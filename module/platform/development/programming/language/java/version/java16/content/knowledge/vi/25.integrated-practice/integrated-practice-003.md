# Xây pipeline lọc kiểu bằng instanceof, mapMulti và toList

Một luồng dữ liệu tích hợp thường nhận nhiều loại object: sự kiện nghiệp vụ hợp lệ, chuỗi lỗi từ nguồn ngoài, giá trị null hoặc kiểu dữ liệu của hệ thống khác. Trước khi xử lý, ứng dụng cần lọc đúng kiểu; sau đó một sự kiện có thể được chuyển thành một hoặc nhiều bản ghi kết quả.

Java 16 cung cấp ba thành phần phù hợp để xây dựng pipeline này:

- **Pattern matching for instanceof** kiểm tra kiểu và tạo biến đã được ép kiểu an toàn ngay trong nhánh đúng.
- **Stream.mapMulti()** phát ra không, một hoặc nhiều phần tử cho mỗi phần tử đầu vào.
- **Stream.toList()** kết thúc pipeline và thu kết quả thành danh sách không thể sửa đổi.

Bài thực hành xây một pipeline xử lý sự kiện đơn hàng. Pipeline nhận dữ liệu hỗn hợp, chỉ giữ các đối tượng triển khai **OrderEvent**, chuyển từng loại sự kiện thành các bản ghi kiểm toán và có thể phát ra nhiều bản ghi cho một sự kiện. Kết quả cuối cùng được thu bằng **toList()**.

## 1. Bài toán thực tế

Giả sử một ứng dụng nhận dữ liệu từ nhiều adapter. Adapter trả về **Object** vì dữ liệu có thể đến từ plugin hoặc thư viện tích hợp khác nhau.

Nguồn đầu vào có thể chứa:

- Sự kiện tạo đơn hàng.
- Sự kiện thanh toán.
- Sự kiện hủy đơn.
- Chuỗi thông báo không thuộc giao thức.
- Giá trị null.
- Một implementation **OrderEvent** mới được bổ sung sau này.

Ứng dụng cần:

1. Kiểm tra kiểu dữ liệu.
2. Loại bỏ giá trị không phải sự kiện đơn hàng.
3. Nhận diện loại sự kiện cụ thể.
4. Chuyển sự kiện thành bản ghi kiểm toán.
5. Cho phép một sự kiện tạo ra nhiều bản ghi.
6. Thu kết quả theo đúng thứ tự nguồn nếu stream có encounter order.

Đây là bài toán lọc kiểu kết hợp với phép biến đổi một-nhiều.

## 2. Khai báo mô hình dữ liệu bằng record

Java 16 đưa record thành tính năng chính thức. Record phù hợp để biểu diễn dữ liệu truyền qua pipeline vì compiler tự sinh constructor canonical, accessor, equals(), hashCode() và toString().

Ta định nghĩa một interface chung cho sự kiện và ba record cụ thể:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

interface OrderEvent {
}

record OrderCreated(
        String orderId,
        BigDecimal total
) implements OrderEvent {
    OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(total, "total");
    }
}

record OrderPaid(
        String orderId,
        BigDecimal amount
) implements OrderEvent {
    OrderPaid {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");
    }
}

record OrderCancelled(
        String orderId,
        String reason
) implements OrderEvent {
    OrderCancelled {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(reason, "reason");
    }
}

record AuditEntry(
        String orderId,
        String action,
        String detail
) {
}
~~~

**OrderEvent** là kiểu cha chung. Các record giúp dữ liệu của từng loại sự kiện có cấu trúc rõ ràng.

OrderEvent là interface thông thường để mô hình vẫn có thể tiếp nhận implementation mới khi hệ thống bổ sung loại sự kiện.

Record có tính bất biến ở mức nông: các component field là final, nhưng nếu một component tham chiếu tới object mutable thì trạng thái object đó vẫn có thể thay đổi. Trong ví dụ, String và BigDecimal là các kiểu bất biến nên phù hợp cho dữ liệu sự kiện.

## 3. Tạo nguồn dữ liệu hỗn hợp

Để mô phỏng dữ liệu từ adapter hoặc plugin, ta tạo một collection có kiểu phần tử là Object:

~~~java
import java.util.Arrays;
import java.util.List;

List<Object> rawEvents = Arrays.asList(
    new OrderCreated("OD-101", new BigDecimal("125.00")),
    "invalid event payload",
    new OrderPaid("OD-102", new BigDecimal("125.00")),
    null,
    new OrderCancelled("OD-103", "customer request"),
    new OrderCreated("OD-104", new BigDecimal("15.00"))
);
~~~

Nguồn có sáu phần tử:

| Thứ tự | Giá trị | Xử lý mong muốn |
| --- | --- | --- |
| 1 | OrderCreated | Giữ lại và tạo bản ghi |
| 2 | Chuỗi | Bỏ qua |
| 3 | OrderPaid | Giữ lại và tạo bản ghi |
| 4 | null | Bỏ qua |
| 5 | OrderCancelled | Giữ lại và tạo bản ghi |
| 6 | OrderCreated | Giữ lại và tạo bản ghi |

Arrays.asList(...) giữ lại cả phần tử null trong nguồn. Mỗi lần gọi rawEvents.stream() tạo một stream mới có encounter order theo thứ tự phần tử trong collection.

Trong ứng dụng thực tế, nguồn có thể là Collection<Object>, kết quả đọc từ message broker hoặc adapter. Các bước pipeline phía sau không phụ thuộc vào cách tạo nguồn.

## 4. Lọc kiểu bằng pattern matching for instanceof

Cách viết truyền thống thường kiểm tra kiểu rồi ép kiểu riêng:

~~~java
if (value instanceof OrderEvent) {
    OrderEvent event = (OrderEvent) value;
    process(event);
}
~~~

Pattern matching for instanceof gộp hai bước này:

~~~java
if (value instanceof OrderEvent event) {
    process(event);
}
~~~

Nếu value là OrderEvent, JVM thực hiện phép kiểm tra kiểu và biến pattern event được tạo với kiểu OrderEvent. Biến này chỉ có phạm vi sử dụng tại nơi compiler xác định phép kiểm tra đã thành công.

Trong Java 16, pattern matching for instanceof đã là tính năng chính thức, không cần bật preview flag. Đây là JEP 394.

## 5. Dùng mapMulti để lọc và thu hẹp kiểu

filter() chỉ quyết định giữ hoặc bỏ phần tử. Sau một phép filter(value -> value instanceof OrderEvent), kiểu tĩnh của stream vẫn là Stream<Object>. Muốn chuyển thành Stream<OrderEvent>, cần thêm bước ép kiểu.

Có thể dùng mapMulti() để kết hợp kiểm tra kiểu, trích xuất biến đã ép kiểu và phát ra phần tử hợp lệ:

~~~java
Stream<OrderEvent> orderEvents = rawEvents.stream()
    .<OrderEvent>mapMulti((value, downstream) -> {
        if (value instanceof OrderEvent event) {
            downstream.accept(event);
        }
    });
~~~

Ý nghĩa của đoạn code:

- Mỗi value được kiểm tra bằng pattern matching.
- Nếu là OrderEvent, phát chính object đó qua downstream.accept(event).
- Nếu không đúng kiểu hoặc là null, không phát phần tử nào.
- Kiểu đầu ra được xác định rõ là OrderEvent.

Đây là phép biến đổi từ một phần tử Object thành không hoặc một phần tử OrderEvent.

### Vì sao cần chỉ định kiểu đầu ra?

mapMulti() có chữ ký tổng quát:

~~~java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
~~~

Trong đó T là kiểu phần tử đầu vào và R là kiểu phần tử được phát ra. Với lambda có Consumer làm tham số, đôi khi compiler không suy luận được R chỉ từ nội dung lambda.

Cú pháp:

~~~java
.<OrderEvent>mapMulti(...)
~~~

chỉ rõ kiểu đầu ra là OrderEvent. Đây là cách viết được tài liệu Stream API sử dụng cho trường hợp lọc Number thành Integer.

## 6. Dùng mapMulti để mở rộng một sự kiện thành nhiều bản ghi

Sau bước lọc, mỗi phần tử là OrderEvent. Ta tiếp tục chuyển từng loại sự kiện thành một hoặc nhiều AuditEntry.

Quy tắc nghiệp vụ:

- OrderCreated luôn tạo một bản ghi ORDER_CREATED.
- Nếu tổng tiền đạt ngưỡng 100.00, tạo thêm bản ghi HIGH_VALUE.
- OrderPaid tạo một bản ghi PAYMENT_RECEIVED.
- OrderCancelled tạo một bản ghi ORDER_CANCELLED.
- Một implementation OrderEvent chưa được xử lý sẽ không phát bản ghi nào.

Code:

~~~java
BigDecimal highValueThreshold = new BigDecimal("100.00");

Stream<AuditEntry> auditStream = orderEvents
    .<AuditEntry>mapMulti((event, downstream) -> {
        if (event instanceof OrderCreated created) {
            downstream.accept(new AuditEntry(
                created.orderId(),
                "ORDER_CREATED",
                "total=" + created.total()
            ));

            if (created.total().compareTo(highValueThreshold) >= 0) {
                downstream.accept(new AuditEntry(
                    created.orderId(),
                    "HIGH_VALUE",
                    "threshold=" + highValueThreshold
                ));
            }
        } else if (event instanceof OrderPaid paid) {
            downstream.accept(new AuditEntry(
                paid.orderId(),
                "PAYMENT_RECEIVED",
                "amount=" + paid.amount()
            ));
        } else if (event instanceof OrderCancelled cancelled) {
            downstream.accept(new AuditEntry(
                cancelled.orderId(),
                "ORDER_CANCELLED",
                "reason=" + cancelled.reason()
            ));
        }
    });
~~~

Ở đây pattern matching tạo các biến có kiểu cụ thể:

- created có kiểu OrderCreated.
- paid có kiểu OrderPaid.
- cancelled có kiểu OrderCancelled.

Không cần ép kiểu thủ công để đọc các component của record.

Một OrderCreated có thể phát một hoặc hai AuditEntry. OrderPaid và OrderCancelled phát một phần tử. Nếu không nhánh nào khớp, mapper không gọi consumer nên phần tử đầu ra bằng không.

Đây chính là điểm khác biệt quan trọng giữa map() và mapMulti():

| Operation | Số phần tử đầu ra cho mỗi phần tử đầu vào |
| --- | --- |
| map() | Chính xác một |
| filter() | Không hoặc một |
| flatMap() | Không, một hoặc nhiều phần tử từ stream con |
| mapMulti() | Không, một hoặc nhiều phần tử được phát qua consumer |

## 7. Thu kết quả bằng Stream.toList()

toList() là terminal operation được thêm vào Stream API từ Java 16.

Hoàn thiện pipeline:

~~~java
BigDecimal highValueThreshold = new BigDecimal("100.00");

List<AuditEntry> auditEntries = rawEvents.stream()
    .<OrderEvent>mapMulti((value, downstream) -> {
        if (value instanceof OrderEvent event) {
            downstream.accept(event);
        }
    })
    .<AuditEntry>mapMulti((event, downstream) -> {
        if (event instanceof OrderCreated created) {
            downstream.accept(new AuditEntry(
                created.orderId(),
                "ORDER_CREATED",
                "total=" + created.total()
            ));

            if (created.total().compareTo(highValueThreshold) >= 0) {
                downstream.accept(new AuditEntry(
                    created.orderId(),
                    "HIGH_VALUE",
                    "threshold=" + highValueThreshold
                ));
            }
        } else if (event instanceof OrderPaid paid) {
            downstream.accept(new AuditEntry(
                paid.orderId(),
                "PAYMENT_RECEIVED",
                "amount=" + paid.amount()
            ));
        } else if (event instanceof OrderCancelled cancelled) {
            downstream.accept(new AuditEntry(
                cancelled.orderId(),
                "ORDER_CANCELLED",
                "reason=" + cancelled.reason()
            ));
        }
    })
    .toList();
~~~

Khi gọi toList(), các intermediate operation mới được thực thi và kết quả được tích lũy thành List<AuditEntry>.

Với stream có encounter order, danh sách kết quả giữ thứ tự xuất hiện của các phần tử được phát ra. Trong ví dụ này, nguồn là stream có thứ tự và mapper phát bản ghi theo thứ tự gọi accept().

### toList() trả về danh sách unmodifiable

Danh sách trả về từ Stream.toList() không thể thêm, xóa hoặc thay thế phần tử:

~~~java
auditEntries.add(
    new AuditEntry("OD-999", "MANUAL", "extra")
);
~~~

Lệnh trên ném UnsupportedOperationException.

Cần phân biệt:

| Cách thu thập | Đặc điểm |
| --- | --- |
| stream.toList() | Trả về List unmodifiable |
| stream.collect(Collectors.toList()) | Không có bảo đảm về kiểu triển khai hoặc khả năng sửa đổi |
| stream.collect(Collectors.toUnmodifiableList()) | Trả về List unmodifiable |
| stream.collect(Collectors.toCollection(ArrayList::new)) | Chủ động tạo ArrayList có thể sửa đổi |

Nếu cần danh sách có thể thêm hoặc xóa phần tử, dùng:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

List<AuditEntry> mutableEntries = auditEntries.stream()
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Không dựa vào implementation cụ thể của Stream.toList(). API cũng cho biết danh sách trả về có thể là value-based; tránh dùng ==, identity hash code hoặc đồng bộ hóa trên chính instance danh sách.

Danh sách unmodifiable cũng không tự động làm các phần tử bên trong bất biến. Nếu phần tử chứa object mutable, trạng thái object đó vẫn có thể thay đổi.

## 8. Chương trình hoàn chỉnh

Lưu code sau vào file IntegratedPractice.java. Tất cả record và interface phụ trợ được khai báo cùng file để dễ chạy ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

interface OrderEvent {
}

record OrderCreated(
        String orderId,
        BigDecimal total
) implements OrderEvent {
    OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(total, "total");
    }
}

record OrderPaid(
        String orderId,
        BigDecimal amount
) implements OrderEvent {
    OrderPaid {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");
    }
}

record OrderCancelled(
        String orderId,
        String reason
) implements OrderEvent {
    OrderCancelled {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(reason, "reason");
    }
}

record AuditEntry(
        String orderId,
        String action,
        String detail
) {
}

public class IntegratedPractice {

    public static void main(String[] args) {
        BigDecimal highValueThreshold =
            new BigDecimal("100.00");

        List<AuditEntry> auditEntries = Stream.<Object>of(
            new OrderCreated("OD-101", new BigDecimal("125.00")),
            "invalid event payload",
            new OrderPaid("OD-102", new BigDecimal("125.00")),
            null,
            new OrderCancelled("OD-103", "customer request"),
            new OrderCreated("OD-104", new BigDecimal("15.00"))
        )
        .<OrderEvent>mapMulti((value, downstream) -> {
            if (value instanceof OrderEvent event) {
                downstream.accept(event);
            }
        })
        .<AuditEntry>mapMulti((event, downstream) -> {
            if (event instanceof OrderCreated created) {
                downstream.accept(new AuditEntry(
                    created.orderId(),
                    "ORDER_CREATED",
                    "total=" + created.total()
                ));

                if (created.total().compareTo(highValueThreshold) >= 0) {
                    downstream.accept(new AuditEntry(
                        created.orderId(),
                        "HIGH_VALUE",
                        "threshold=" + highValueThreshold
                    ));
                }
            } else if (event instanceof OrderPaid paid) {
                downstream.accept(new AuditEntry(
                    paid.orderId(),
                    "PAYMENT_RECEIVED",
                    "amount=" + paid.amount()
                ));
            } else if (event instanceof OrderCancelled cancelled) {
                downstream.accept(new AuditEntry(
                    cancelled.orderId(),
                    "ORDER_CANCELLED",
                    "reason=" + cancelled.reason()
                ));
            }
        })
        .toList();

        auditEntries.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy bằng JDK 16:

~~~bash
javac IntegratedPractice.java
java IntegratedPractice
~~~

Nếu dùng JDK mới hơn nhưng muốn xác nhận code tương thích Java 16, có thể biên dịch với:

~~~bash
javac --release 16 IntegratedPractice.java
java IntegratedPractice
~~~

--release 16 yêu cầu compiler kiểm tra cú pháp và API theo Java 16.

## 9. Kết quả mong đợi

Chương trình tạo năm bản ghi kiểm toán:

~~~text
AuditEntry[orderId=OD-101, action=ORDER_CREATED, detail=total=125.00]
AuditEntry[orderId=OD-101, action=HIGH_VALUE, detail=threshold=100.00]
AuditEntry[orderId=OD-102, action=PAYMENT_RECEIVED, detail=amount=125.00]
AuditEntry[orderId=OD-103, action=ORDER_CANCELLED, detail=reason=customer request]
AuditEntry[orderId=OD-104, action=ORDER_CREATED, detail=total=15.00]
~~~

Có sáu phần tử đầu vào nhưng chỉ bốn phần tử là OrderEvent. Chuỗi và null không tạo kết quả. Trong bốn sự kiện hợp lệ, sự kiện tạo đơn hàng OD-101 phát ra hai bản ghi vì tổng tiền đạt ngưỡng. Ba sự kiện còn lại mỗi sự kiện phát ra một bản ghi.

Tổng kết số lượng:

| Thành phần | Số lượng |
| --- | ---: |
| Phần tử đầu vào | 6 |
| Sự kiện hợp lệ | 4 |
| Giá trị bị loại | 2 |
| Bản ghi từ OD-101 | 2 |
| Bản ghi từ các sự kiện còn lại | 3 |
| Tổng kết quả | 5 |

## 10. So sánh mapMulti với flatMap

flatMap() cũng hỗ trợ biến đổi một phần tử thành nhiều phần tử bằng cách trả về một stream con:

~~~java
Stream<OrderEvent> events = rawEvents.stream()
    .filter(OrderEvent.class::isInstance)
    .map(OrderEvent.class::cast);

Stream<AuditEntry> auditStream = events.flatMap(event -> {
    if (event instanceof OrderPaid paid) {
        return Stream.of(new AuditEntry(
            paid.orderId(),
            "PAYMENT_RECEIVED",
            "amount=" + paid.amount()
        ));
    }

    return Stream.empty();
});
~~~

Với flatMap(), mapper phải trả về một Stream cho mỗi phần tử. Với mapMulti(), mapper nhận một consumer và gọi consumer zero or more times để phát phần tử.

| Tiêu chí | flatMap() | mapMulti() |
| --- | --- | --- |
| Cách phát kết quả | Trả về stream con | Gọi consumer |
| Số kết quả | 0..N | 0..N |
| Phong cách code | Functional, trả về stream | Imperative, phát từng phần tử |
| Trường hợp phù hợp | Biến đổi tự nhiên thành stream con | Tạo một số ít kết quả hoặc nhánh có thể không tạo kết quả |
| Chi phí | Có stream con cho từng nhóm kết quả | Có thể tránh tạo stream con ở implementation tối ưu |

Tài liệu API khuyến nghị cân nhắc mapMulti() khi mỗi phần tử tạo ra một số lượng kết quả nhỏ, có thể bằng không, hoặc khi cách viết imperative dễ hiểu hơn việc tạo stream con.

Không nên kết luận mapMulti() luôn nhanh hơn flatMap(). Implementation mặc định của API có thể dùng buffer nội bộ rồi gọi flatMap(). JVM hoặc stream implementation cụ thể có thể cung cấp cách triển khai tối ưu hơn. Hãy benchmark trên dữ liệu và JDK thực tế nếu hiệu năng là tiêu chí quyết định.

## 11. Khi nào nên dùng filter và map?

Nếu chỉ cần lọc phần tử theo kiểu mà không mở rộng thành nhiều kết quả, có thể dùng filter() kết hợp với map():

~~~java
List<OrderEvent> events = rawEvents.stream()
    .filter(value -> value instanceof OrderEvent)
    .map(value -> (OrderEvent) value)
    .toList();
~~~

Hoặc dùng Class.isInstance() và Class.cast() khi kiểu cần lọc được cung cấp dưới dạng Class:

~~~java
List<OrderEvent> events = rawEvents.stream()
    .filter(OrderEvent.class::isInstance)
    .map(OrderEvent.class::cast)
    .toList();
~~~

Hai bước này phù hợp khi chỉ cần giữ nguyên một object cho mỗi phần tử hợp lệ.

Nếu cần kiểm tra kiểu và trích xuất biến pattern trong cùng một bước, có thể dùng mapMulti():

~~~java
List<OrderEvent> events = rawEvents.stream()
    .<OrderEvent>mapMulti((value, downstream) -> {
        if (value instanceof OrderEvent event) {
            downstream.accept(event);
        }
    })
    .toList();
~~~

Khi mỗi phần tử tiếp tục tạo ra nhiều kết quả, mapMulti() thể hiện rõ mục đích hơn.

## 12. Quy tắc sử dụng consumer trong mapMulti

Consumer được truyền vào mapper là cách duy nhất để phát phần tử cho downstream pipeline.

Giả sử input có kiểu Stream<String>. Có thể gọi consumer nhiều lần:

~~~java
Stream<String> cleaned = input.<String>mapMulti((value, downstream) -> {
    downstream.accept(value);
    downstream.accept(value.toUpperCase());
});
~~~

Có thể không gọi lần nào để loại bỏ phần tử:

~~~java
Stream<String> nonBlank = input.<String>mapMulti((value, downstream) -> {
    if (value != null && !value.isBlank()) {
        downstream.accept(value);
    }
});
~~~

Không lưu consumer vào field, collection hoặc biến dùng sau callback. Không chuyển consumer sang thread khác hoặc gọi nó sau khi mapper đã kết thúc. Tài liệu API quy định kết quả là undefined nếu consumer được sử dụng ngoài phạm vi mapper function.

Mapper cần không can thiệp vào nguồn stream và nên stateless. Không dùng mapMulti() để thay đổi collection nguồn trong khi pipeline đang đọc collection đó.

## 13. Thứ tự và xử lý parallel stream

Pipeline trong bài bắt đầu bằng Stream.of(), là stream có thứ tự. toList() giữ encounter order nếu nguồn có thứ tự.

Nếu chuyển sang parallel stream, không nên dùng biến mutable dùng chung để tự tích lũy kết quả:

~~~java
// Không nên: nhiều nhánh xử lý cùng ghi vào ArrayList này.
List<AuditEntry> result = new java.util.ArrayList<>();
~~~

Hãy phát kết quả bằng consumer mà pipeline cung cấp. Stream API quản lý việc chuyển kết quả qua các giai đoạn và terminal operation.

Với pipeline parallel, mapper phải không phụ thuộc vào trạng thái thay đổi giữa các lần gọi. Ngưỡng highValueThreshold trong ví dụ là biến local không thay đổi, nên có thể được đọc an toàn trong mapper.

Tuy nhiên, parallel không mặc định nhanh hơn. Với số lượng phần tử nhỏ hoặc phép biến đổi nhẹ, chi phí chia công việc và phối hợp có thể lớn hơn lợi ích. Chỉ chuyển sang parallel sau khi đo bằng workload thực tế.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Compiler không suy luận được kiểu đầu ra | Lambda mapMulti() chưa cung cấp đủ thông tin generic | Ghi rõ .<OrderEvent>mapMulti(...) hoặc .<AuditEntry>mapMulti(...) |
| ClassCastException | Ép kiểu mà không kiểm tra kiểu đầu vào | Dùng pattern matching với instanceof |
| NullPointerException | Truy cập component trước khi loại bỏ null | Kiểm tra kiểu trước khi đọc component |
| Không có kết quả cho một loại event | Nhánh xử lý không gọi consumer | Thêm nhánh phát kết quả hoặc xác định rõ loại đó bị bỏ qua |
| UnsupportedOperationException khi thêm phần tử | Danh sách từ toList() là unmodifiable | Dùng Collectors.toCollection(ArrayList::new) nếu cần mutable list |
| Kết quả bị lặp | Mapper gọi consumer nhiều lần ngoài ý muốn | Xác định số lần phát cho từng loại đầu vào |
| Kết quả không đúng thứ tự mong muốn | Nguồn stream không có encounter order hoặc xử lý không giữ thứ tự | Xác định rõ yêu cầu ordering và chọn nguồn/operation phù hợp |
| Kết quả sai khi chạy parallel | Mapper thay đổi trạng thái dùng chung | Viết mapper stateless và non-interfering |
| Lỗi khó tái hiện do consumer | Consumer bị lưu và gọi sau callback | Chỉ gọi consumer ngay bên trong mapper |

## 15. Mở rộng pipeline trong ứng dụng thực tế

Sau khi có List<AuditEntry>, ứng dụng có thể tiếp tục xử lý theo nghiệp vụ:

- Lưu audit entries vào database.
- Gửi sự kiện tới message broker.
- Nhóm theo orderId.
- Thống kê số lượng sự kiện theo action.
- Chuyển thành JSON để ghi log hoặc gửi API.
- Lọc theo ngưỡng, trạng thái hoặc loại khách hàng.

Ví dụ nhóm bản ghi theo action:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<AuditEntry>> entriesByAction =
    auditEntries.stream()
        .collect(Collectors.groupingBy(AuditEntry::action));
~~~

Ví dụ đếm số bản ghi theo action:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByAction =
    auditEntries.stream()
        .collect(Collectors.groupingBy(
            AuditEntry::action,
            Collectors.counting()
        ));
~~~

Những thao tác này sử dụng các API Stream và Collectors tiêu chuẩn. Không cần một thư viện xử lý pipeline riêng cho bài toán lọc kiểu và phát nhiều kết quả đơn giản.

## 16. Checklist đánh giá pipeline

- [ ] Nguồn dữ liệu có kiểu phần tử được xác định rõ.
- [ ] Dữ liệu không đúng kiểu và null được xử lý có chủ đích.
- [ ] Pattern variable chỉ được sử dụng trong phạm vi compiler xác định là an toàn.
- [ ] Kiểu đầu ra của mapMulti() được khai báo rõ khi cần.
- [ ] Mỗi nhánh gọi consumer đúng số lần cần thiết.
- [ ] Consumer không bị sử dụng ngoài callback.
- [ ] Mapper không can thiệp vào nguồn và không phụ thuộc trạng thái mutable dùng chung.
- [ ] toList() được dùng khi cần kết quả unmodifiable.
- [ ] Dùng ArrayList hoặc collection mutable khác khi nghiệp vụ cần sửa danh sách.
- [ ] Đã xác nhận encounter order có phù hợp với yêu cầu không.
- [ ] Đã benchmark nếu chọn mapMulti() vì lý do hiệu năng.

## 17. Kết luận

Pipeline trong bài kết hợp ba tính năng chính thức từ Java 16. Record biểu diễn các loại sự kiện và bản ghi kết quả. Pattern matching for instanceof kiểm tra kiểu và tạo biến đã được ép kiểu an toàn. mapMulti() lọc các đối tượng không hợp lệ, sau đó chuyển mỗi sự kiện thành không, một hoặc nhiều bản ghi kiểm toán. Cuối cùng, toList() thực thi pipeline và thu kết quả thành danh sách unmodifiable.

Khi xây pipeline thực tế, hãy chọn operation theo số lượng đầu ra cần tạo: filter() cho lọc, map() cho một-một, flatMap() hoặc mapMulti() cho không-một-nhiều. Dùng toList() khi danh sách kết quả không cần thay đổi; nếu cần mutable collection, hãy chọn factory rõ ràng. Các API này vẫn là thành phần tiêu chuẩn trong Java hiện đại và không cần preview flag.

## Tài liệu tham khảo

- [Java Language Changes — Java SE 16](https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html)
- [JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395: Records](https://openjdk.org/jeps/395)
- [Stream API — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [Stream API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Collectors API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)

