# Mã định danh chưa được gán và rủi ro thay đổi quan hệ bằng nhau trong Java

## 1. Vấn đề cần giải quyết

Trong một ứng dụng có **entity** (thực thể có danh tính tồn tại qua thời gian), hai object Java khác nhau có thể cùng đại diện cho một thực thể nghiệp vụ; ngược lại, hai object có nội dung trông giống nhau có thể đại diện cho hai thực thể khác nhau. Khi ID của entity được cơ sở dữ liệu cấp sau lúc tạo object, trường `id` ban đầu thường là `null`. Giai đoạn này đặt ra câu hỏi: **thế nào là bằng nhau khi ID chưa có, và điều gì xảy ra khi ID đổi từ `null` sang giá trị thật?**

Ví dụ sau chỉ minh họa trạng thái; lớp `Order` và constructor chưa được định nghĩa tại đây:

```java
Order first = new Order(null, "CUSTOMER-7");
Order second = new Order(null, "CUSTOMER-7");
```

Hai câu lệnh `new` tạo hai tham chiếu đến hai object khác nhau. Nếu đây là hai đơn hàng mới độc lập, chúng **không** nên bị xem là cùng entity chỉ vì ID đều `null` hoặc cùng mã khách hàng. Mặt khác, sau khi lưu, hai object được tải ở những thời điểm khác nhau với cùng ID có thể được coi là bằng nhau về danh tính nghiệp vụ.

Mục tiêu sau bài học:
- Chọn quy tắc `equals` phù hợp khi ID chưa được gán.
- Hiểu vì sao `Objects.equals(null, null)` thường gây lỗi trong mô hình entity có ID cấp sau.
- Nhận diện tác động khi một trường tham gia `equals`/`hashCode` thay đổi trong khi object đang nằm trong `HashSet` hoặc là khóa `HashMap`.
- Phân biệt cách dùng ID cấp sau, ID ứng dụng cấp ngay và khóa nghiệp vụ bất biến.
- Kiểm tra hành vi bằng một chương trình Java 17 độc lập, giải thích chính xác các kết quả.

Bối cảnh là **Java Core và quan hệ bằng nhau**. Với JPA/Hibernate, cách tạo proxy và quản lý entity theo từng phiên bản cần được xét thêm; ví dụ thuần Java ở đây không phải một class ORM hoàn chỉnh.

## 2. Danh tính tham chiếu, danh tính entity và giá trị

| Khái niệm | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| Object identity | Có đúng là cùng một object Java không? | `a == b` |
| Entity identity | Có đại diện cho cùng một thực thể nghiệp vụ qua các lần tải không? | ID đã xác nhận hoặc khóa nghiệp vụ được thiết kế |
| Value equality | Có cùng nội dung giá trị có ý nghĩa không? | `equals` theo các thành phần bất biến đã chọn |

`Object.equals` mặc định dùng danh tính tham chiếu. Khi ghi đè, ta phải định nghĩa một **quan hệ tương đương** có các tính chất phản xạ, đối xứng, bắc cầu; nhất quán nếu dữ liệu dùng so sánh không đổi; và `x.equals(null) == false`.

`hashCode` phải tuân thủ: nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`. Chiều đảo không bắt buộc đúng: hai entity khác nhau có thể có cùng hash. Khi một object đang được dùng làm khóa dựa trên hash, các dữ liệu làm thay đổi hash của nó không nên thay đổi trong thời gian lưu trữ.

### Vòng đời thường gặp của ID cấp bởi nơi lưu trữ

| Thời điểm | Object | ID | Ý nghĩa |
|---|---|---|---|
| Vừa tạo | `a` | `null` | Một entity mới; so bằng tham chiếu với chính nó |
| Cùng lúc tạo mới khác | `b` | `null` | Entity mới khác; `a.equals(b)` thường phải `false` |
| Sau khi được cấp ID | `a` | `101` | Danh tính bền vững bắt đầu có thể so theo ID |
| Được tải lại | `c` | `101` | `a != c` nhưng có thể `a.equals(c)` |
| Một entity khác | `d` | `102` | Không bằng entity ID `101` |

Không nên giả định ID được cấp ngay sau một lệnh `persist` hay `save`: thời điểm phụ thuộc chiến lược sinh ID, ORM, giao dịch, flush và lệnh INSERT thực tế.

## 3. Sai lầm thứ nhất: hai ID `null` được coi là bằng nhau

Một cách triển khai thiếu điều kiện:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Order that)) {
        return false;
    }
    return Objects.equals(id, that.id);
}
```

Đoạn này là minh họa riêng, không phải file Java độc lập. `Objects.equals(null, null)` trả `true`. Nếu `a` và `b` là hai entity mới độc lập, cả hai có `id == null`, biểu thức này sẽ khiến `a.equals(b)` trả `true` dù không có cơ sở để khẳng định chúng cùng entity.

Hậu quả khi đưa vào collection:
- `HashSet` có thể loại một object mới vì tưởng nó trùng entity đang có.
- `HashMap.put(b, value)` có thể ghi đè giá trị lưu với khóa `a`.
- Các phép kiểm tra tồn tại/loại trùng có thể làm mất dữ liệu logic dù entity chưa được lưu.

Nếu chọn chính sách **chỉ so theo ID đã gán**, cần kiểm tra ID khác `null`:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Order that)) {
        return false;
    }
    return id != null && id.equals(that.id);
}
```

Ở đây `this == other` bảo đảm phản xạ ngay cả khi ID chưa được cấp. Kiểm tra kiểu phù hợp với lớp `final` minh họa. Với cây kế thừa hoặc ORM proxy, phải xác định lại cách so kiểu sao cho đối xứng, không phá identity.

## 4. Sai lầm thứ hai: hash thay đổi khi ID được gán

Nếu `hashCode` trả về `Objects.hashCode(id)`:
- ID `null` → hash bằng `0`.
- ID là `Long.valueOf(100)` → hash bằng `100`.

Đưa object vào `HashSet` khi hash là `0` rồi cập nhật ID khiến hash thành `100` có thể làm việc tìm kiếm thất bại. Collection dùng hash để định hướng bucket; nó không tự chuyển phần tử sang bucket mới khi thuộc tính của object thay đổi.

Một lỗi thường gặp khác:

```java
@Override
public int hashCode() {
    return id.hashCode();
}
```

Nếu ID chưa có thì đoạn trên ném `NullPointerException`. Đổi thành `Objects.hashCode(id)` chỉ tránh NPE, chưa giải quyết được vấn đề hash đổi khi ID xuất hiện.

Cũng không được dùng các trường mutable khác làm hash chỉ để “ổn định tạm thời” nếu chúng có thể sửa về sau, hoặc có thể khác nhau giữa hai object mang cùng ID. Nếu `equals` coi hai entity cùng ID là bằng nhau nhưng hash dựa trên trạng thái khác nhau, hợp đồng `equals`/`hashCode` bị phá.

## 5. Sai lầm thứ ba: quan hệ bằng nhau chuyển trạng thái

Đặc điểm tinh vi hơn là **kết quả `equals` giữa hai object có thể đổi theo vòng đời**. Ví dụ, trước khi ID được cấp, hai object mới `a` và `b` khác tham chiếu không bằng nhau; sau đó nếu cả hai được liên kết với cùng ID thực thể, `a.equals(b)` có thể đổi thành `true`.

Hợp đồng `equals` của Java yêu cầu nhất quán **khi thông tin dùng so sánh không bị sửa**. Do đó thay đổi quan hệ khi ID thay đổi không nhất thiết vi phạm riêng điều kiện nhất quán của `equals`. Tuy nhiên, **collection không tự tính lại các cặp bằng nhau**. Nếu hai object được thêm khi chúng còn khác nhau, rồi sau đó trở thành bằng nhau, `HashSet` có thể vẫn giữ cả hai. Hash ổn định chưa đủ để chữa loại vấn đề này.

Đây là lý do phải xét cả **thời điểm thêm object vào collection** và **liệu equality còn có thể đổi trong thời gian lưu trữ**.

## 6. Ví dụ Java 17: tái hiện lỗi và hai hướng xử lý

Tạo file **`UnassignedIdDemo.java`**. Ba lớp lồng đều `final` nhằm giữ phép so kiểu đơn giản:
- `BadOrder` minh họa lỗi `null/null` và hash thay đổi.
- `GeneratedOrder` minh họa ID cấp sau, `equals` phân biệt entity mới và hash cố định theo lớp.
- `ClientAssignedOrder` minh họa ID bất biến có ngay khi tạo object.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class UnassignedIdDemo {
    public static void main(String[] args) {
        BadOrder bad = new BadOrder();
        BadOrder anotherBad = new BadOrder();

        System.out.println("bad null IDs equal: "
                + bad.equals(anotherBad));

        Set<BadOrder> badSet = new HashSet<>();
        badSet.add(bad);
        System.out.println("bad hash before: " + bad.hashCode());
        System.out.println("bad contains before: "
                + badSet.contains(bad));

        bad.assignId(100L);
        System.out.println("bad hash after: " + bad.hashCode());
        System.out.println("bad contains after: "
                + badSet.contains(bad));

        GeneratedOrder first = new GeneratedOrder();
        GeneratedOrder second = new GeneratedOrder();
        System.out.println("safe null IDs equal: "
                + first.equals(second));

        Set<GeneratedOrder> safeSet = new HashSet<>();
        safeSet.add(first);
        first.assignId(100L);
        System.out.println("safe contains after: "
                + safeSet.contains(first));

        second.assignId(100L);
        System.out.println("safe same persisted ID: "
                + first.equals(second));
        System.out.println("safe lookup by second: "
                + safeSet.contains(second));

        UUID key1 = UUID.fromString(
                "00000000-0000-0000-0000-000000000001");
        UUID key2 = UUID.fromString(
                "00000000-0000-0000-0000-000000000002");

        ClientAssignedOrder assigned1 = new ClientAssignedOrder(key1);
        ClientAssignedOrder sameId = new ClientAssignedOrder(key1);
        ClientAssignedOrder assigned2 = new ClientAssignedOrder(key2);

        System.out.println("assigned same ID: "
                + assigned1.equals(sameId));
        System.out.println("assigned different ID: "
                + assigned1.equals(assigned2));
    }

    // CỐ Ý SAI: null/null bị coi là cùng entity và hash đổi theo ID.
    static final class BadOrder {
        private Long id;

        void assignId(long value) {
            if (value <= 0) {
                throw new IllegalArgumentException("invalid ID");
            }
            if (id != null) {
                throw new IllegalStateException("ID already assigned");
            }
            id = value;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadOrder that
                    && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    // Entity có ID cấp sau: null không bằng ID của instance khác.
    static final class GeneratedOrder {
        private Long id;

        void assignId(long value) {
            if (value <= 0) {
                throw new IllegalArgumentException("invalid ID");
            }
            if (id != null) {
                throw new IllegalStateException("ID already assigned");
            }
            id = value;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof GeneratedOrder that)) {
                return false;
            }
            return id != null && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            // Cố định theo lớp thay vì ID mutable.
            return GeneratedOrder.class.hashCode();
        }
    }

    // Entity có ID ứng dụng cấp trước; ID final.
    static final class ClientAssignedOrder {
        private final UUID id;

        ClientAssignedOrder(UUID id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        static ClientAssignedOrder createNew() {
            return new ClientAssignedOrder(UUID.randomUUID());
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof ClientAssignedOrder that
                    && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 UnassignedIdDemo.java
java UnassignedIdDemo
```

Output trên triển khai `HashSet`/`HashMap` thông dụng của JDK 17:

```text
bad null IDs equal: true
bad hash before: 0
bad contains before: true
bad hash after: 100
bad contains after: false
safe null IDs equal: false
safe contains after: true
safe same persisted ID: true
safe lookup by second: true
assigned same ID: true
assigned different ID: false
```

**Giải thích theo từng khối:**

1. `BadOrder` sai vì `Objects.equals(null, null)` là `true`. Việc gán ID `100L` làm hash đổi từ `0` sang `100`; với bucket trong bản JDK 17 thông dụng, `HashSet.contains(bad)` sau cập nhật trả `false`. Về mặt hợp đồng, tra cứu sau khi thay đổi hash của phần tử đang lưu **không được bảo đảm**; không nên suy rộng rằng mọi phiên bản hay mọi giá trị ID đều phải in `false`.
2. `GeneratedOrder` không coi hai object mới ID `null` là bằng nhau. Object so với chính nó vẫn bằng nhau nhờ `this == other`. Hash cố định theo lớp nên ID được cấp sau khi object đã nằm trong `HashSet` không làm đổi bucket.
3. `first` và `second` sau khi cùng nhận ID `100` đại diện cùng entity trong tình huống mô phỏng. `equals` trả `true` và hash như nhau, nên có thể tra phần tử trong `safeSet` bằng `second`.
4. `ClientAssignedOrder` dùng ID `UUID` là trường `final`, có nghĩa là hash ổn định. Hai object mang cùng ID được coi là bằng nhau; hai ID xác định khác nhau thì khác nhau. `createNew()` dùng `UUID.randomUUID()` khi tạo entity thực tế nhưng không dùng trong output để chương trình luôn in kết quả xác định.

### Hash cố định có thật sự đúng không?

Với `GeneratedOrder` là lớp `final`, mọi instance trả `GeneratedOrder.class.hashCode()`. Nếu hai entity bằng nhau thì hash chắc chắn bằng nhau, nên hợp đồng hash vẫn được tuân thủ. Tuy nhiên, tất cả instance cùng lớp có cùng hash, gây nhiều collision và có thể làm thao tác collection chậm khi có số lượng lớn. Đây là lựa chọn có đánh đổi, không phải đáp án tối ưu trong mọi bối cảnh.

Giá trị `Class.hashCode()` ở đây được dùng làm hash trong **bộ nhớ JVM**, không phải ID có thể lưu hoặc truyền giữa các tiến trình. Không được dựa vào giá trị hash cụ thể để nhận diện bản ghi.

### Hash cố định chưa giữ được tính duy nhất nếu equality đổi

Giả sử thêm hai object `GeneratedOrder` mới khác nhau vào `HashSet` khi ID đều `null`. Tập sẽ có hai phần tử vì chúng không bằng nhau. Nếu một lỗi đồng bộ khiến cả hai sau đó mang cùng ID, chúng trở thành bằng nhau nhưng tập không tự loại phần tử trùng. Do đó, lựa chọn hash cố định chỉ giải quyết **hash bucket ổn định**; ứng dụng vẫn cần quản lý thời điểm ID xuất hiện và thời điểm object được đưa vào collection.

## 7. Ba chiến lược triển khai thực tế

### A. Cấp ID bất biến ngay khi tạo object

Nếu kiến trúc cho phép, ứng dụng có thể cấp UUID ngay trong constructor/factory. `equals` và `hashCode` cùng dựa trên ID bất biến; vì vậy chúng ổn định ngay cả trước khi entity được lưu. Object tải lại phải giữ **đúng ID đã có**, không sinh ID mới.

Cần tính đến giới hạn duy nhất và thiết kế lưu trữ: UUID ngẫu nhiên có xác suất va chạm rất nhỏ nhưng không có bảo đảm toán học tuyệt đối; ID phải tương thích schema và toàn bộ dịch vụ có liên quan.

### B. ID do nơi lưu trữ cấp sau

Khi ID ban đầu `null`, chính sách thường dùng với lớp Java `final` là:

1. Nếu cùng tham chiếu (`this == other`), trả `true`.
2. Nếu không cùng kiểu entity, trả `false`.
3. Nếu ID chưa có, không coi bằng một object khác.
4. Nếu ID đã có, so ID theo ngữ nghĩa nghiệp vụ.
5. Chọn hash ổn định với vòng đời dự kiến hoặc trì hoãn việc đưa object vào hash collection cho tới khi danh tính ổn định.

Cần cân nhắc chi phí của hash cố định và nguy cơ equality đổi với object khác. Một lựa chọn dễ kiểm soát là chỉ tạo khóa hash từ ID **sau khi ID được xác nhận**.

### C. Dùng khóa nghiệp vụ bất biến, duy nhất

Một cặp dữ liệu như `tenantId + externalOrderId` có thể nhận diện entity từ trước lúc database cấp khóa kỹ thuật, **nếu** miền nghiệp vụ thật sự bảo đảm không đổi và duy nhất trong phạm vi đã định nghĩa. Đừng lấy tên khách hàng, email, ghi chú, trạng thái hoặc một thuộc tính có thể sửa làm khóa chỉ vì nó hiện có vẻ duy nhất.

Nếu nghiệp vụ cần sửa khóa, phải tính lại quy tắc identity và hệ quả với collection; khi đó một khóa kỹ thuật cấp ngay có thể phù hợp hơn.

| Tiêu chí | ID ứng dụng cấp ngay | ID database cấp sau + hash cố định | Khóa nghiệp vụ bất biến |
|---|---|---|---|
| ID/khóa sẵn khi tạo | Có | Chưa | Có nếu nghiệp vụ cung cấp |
| Có thể giữ hash ổn định | Có | Có, với hash không dựa ID | Có nếu trường khóa không đổi |
| Equality giữa hai representation | Theo cùng ID | Theo ID sau khi cấp | Theo khóa nghiệp vụ |
| Rủi ro chính | Phân phối/lưu/tái tạo ID không đúng | Collision và equality đổi theo lifecycle | Uniqueness hoặc tính bất biến không như giả định |

## 8. Riêng với ORM/JPA/Hibernate

Không thể bê nguyên `GeneratedOrder` ở trên vào mọi entity ORM: một số provider dùng proxy/subclass, yêu cầu constructor và quy tắc truy cập nhất định. `getClass()` có thể trả lớp proxy, trong khi `instanceof` có thể dẫn đến so sánh không phù hợp trong cây kế thừa. Quy tắc so kiểu phải được thiết kế nhất quán và thử trên provider cụ thể.

Những tình huống cần kiểm tra:
- Entity mới chưa có ID, hai instance mới khác nhau.
- Entity được cấp ID sau khi insert/flush theo chiến lược cụ thể.
- Hai representation của cùng bản ghi được nạp ở những session khác nhau.
- Detached entity và entity sau merge.
- Proxy và non-proxy của cùng entity, nếu provider dùng proxy.
- Các quan hệ lazy hoặc mutable không nên bị kéo vào equality theo cách gây vòng lặp hay truy cập database ngoài ý muốn.

Không suy từ một ví dụ Java thuần ra rằng `persist` luôn cấp ID tức thì, `final` luôn hợp lệ với proxy ORM, hoặc mọi lớp entity đều dùng một mẫu `hashCode` duy nhất.

## 9. Bài tập kiểm tra quan hệ bằng nhau

### Trường hợp cần dự đoán

| Đầu vào | Kết quả theo chính sách ID cấp sau |
|---|---|
| `a.id == null`, so `a.equals(a)` | `true` |
| `a != b`, cả hai ID `null` | `false` |
| `a.id == 101`, `b.id == 101`, cùng kiểu entity | `true` |
| `a.id == 101`, `b.id == 102` | `false` |
| `a.id == 101`, `b.id == null` | `false` |
| `a.equals(null)` | `false` |
| `a.equals(b)` là `true` | `a.hashCode() == b.hashCode()` bắt buộc đúng |
| Object đã lưu trong `HashSet`, sau đó đổi trường tham gia hash | Lookup không còn đáng tin |
| Hai object ở trong `HashSet`, sau đó equality giữa chúng đổi thành `true` | Collection không tự gộp phần tử |

### Các bài tập thực hành

1. Viết các phép kiểm tra phản xạ, đối xứng, bắc cầu cho ba object mang ID `101` và các object còn `null`. Đừng quên so với `null` và so với object kiểu khác.
2. Đổi `GeneratedOrder.hashCode()` sang `Objects.hashCode(id)` trong bản thử riêng. Chạy lại, quan sát thay đổi; giải thích vì sao chỉ nhìn một lần chạy chưa đủ chứng minh thiết kế an toàn.
3. Dùng một object `BadOrder` làm khóa `HashMap` trước khi cấp ID; thử `get` với chính object đó trước và sau khi gán ID. Giải thích vì sao giá trị có thể không tìm lại được.
4. Thêm hai `GeneratedOrder` đang thiếu ID vào một `HashSet`, rồi trong tình huống giả lập gán cùng ID cho chúng. Kiểm tra kích thước tập trước/sau và giải thích vì sao hash cố định không bảo đảm tập tự làm sạch.
5. Viết một value object `OrderKey` bất biến gồm `tenantId` và `orderId` đã có; so sánh độ ổn định khi dùng `OrderKey` làm khóa `Map` so với dùng entity có ID cấp sau.
6. Nếu ứng dụng dùng ORM, viết integration test cho hai session và proxy thực tế, không chỉ unit test với POJO đơn giản.

Một đoạn kiểm tra ý nghĩa equality (dùng lớp lồng `GeneratedOrder` của `UnassignedIdDemo` trong chính file demo, hoặc sửa tên đủ điều kiện khi chuyển ra file khác):

```java
GeneratedOrder a = new GeneratedOrder();
GeneratedOrder b = new GeneratedOrder();

assert a.equals(a);
assert !a.equals(b);
assert !a.equals(null);

a.assignId(101L);
b.assignId(101L);
assert a.equals(b);
assert b.equals(a);
assert a.hashCode() == b.hashCode();
```

Đây là đoạn minh họa **không chạy độc lập**. Trong Java, các câu lệnh `assert` mặc định bị tắt nếu không bật `-ea`; trong dự án thật nên dùng bộ assertion của JUnit hoặc công cụ kiểm thử tương ứng để kết quả luôn được kiểm tra.

## 10. Checklist trước khi đưa entity vào collection

- Danh tính nghiệp vụ có thật sự do ID quyết định không, hay có khóa bất biến khác?
- ID có thể là `null` tại thời điểm đang tạo entity hoặc tạo khóa collection không?
- Hai object mới độc lập có bị đánh đồng chỉ vì cùng ID `null` không?
- `equals` có xét `this == other` để giữ tính phản xạ cho entity chưa có ID không?
- `hashCode` có phụ thuộc vào ID hoặc bất kỳ trường nào còn có thể thay đổi không?
- Hai object đang nằm trong collection có thể chuyển từ khác nhau thành bằng nhau không?
- Khi nạp lại object, có giữ nguyên identity thay vì cấp một ID mới không?
- Nếu dùng ORM, việc so sánh kiểu thực thể và xử lý proxy có làm hỏng đối xứng/bắc cầu hoặc gây truy vấn ngầm không?
- Có thể dùng một khóa bất biến riêng thay vì trực tiếp dùng entity làm khóa `HashMap` không?

**Điểm cần nhớ:** `null` nghĩa là **chưa được gán ID**, không phải một ID chung cho mọi entity mới. Khi ID xuất hiện, quan hệ bằng nhau và mã băm có thể thay đổi; cần chủ động chọn chính sách identity, thiết kế `equals` và `hashCode` nhất quán, và quản lý thời điểm sử dụng entity trong các collection.