# Limit động hoặc giới hạn First/Top trong phạm vi hỗ trợ

Trong chương **Scrolling** của module **SPRING_DATA_COMMONS**, giới hạn kết quả giúp chia việc đọc một tập dữ liệu lớn thành những lượt có kích thước kiểm soát được. Bài này nối ba abstraction: repository query xác định dữ liệu cần đọc, `ScrollPosition` xác định nơi tiếp tục và `Window<T>` chứa kết quả của một lượt.

Mục tiêu thực hành là chọn được giới hạn cố định bằng `First`/`Top`, truyền giới hạn động bằng `Limit`, đồng thời phân biệt kích thước mỗi cửa sổ với hạn mức xử lý của cả tác vụ. Việc thực thi truy vấn thuộc module Spring Data dành cho kho dữ liệu cụ thể; khai báo được một kiểu trong Java chưa chứng minh store hỗ trợ tổ hợp truy vấn đó.

## 1. Xác định giới hạn đang áp dụng ở đâu

Giả sử có 135 đơn hàng đã thanh toán, được xếp theo thời điểm tạo và mã định danh. Một tác vụ xuất dữ liệu muốn đọc từng đợt 50 đơn, nhưng lần chạy này chỉ được xử lý tối đa 120 đơn.

Có hai con số độc lập:

| Khái niệm | Giá trị trong ví dụ | Nơi quyết định |
| --- | --- | --- |
| Kích thước mong muốn của một cửa sổ | 50 đơn | `First50`, `Top50` hoặc `Limit.of(50)` |
| Hạn mức của cả lần chạy | 120 đơn | Logic điều phối trong service |
| Số phần tử thực tế nhận được | Không vượt giới hạn của lượt đọc | Kết quả truy vấn |
| Vị trí để đọc tiếp | Sau phần tử đã đọc cuối cùng | Metadata của `Window` |

Với một scroll query được hỗ trợ, giới hạn cố định trong tên phương thức được áp dụng lại khi lấy cửa sổ tiếp theo. Gọi liên tiếp một phương thức `findFirst50By…` với các vị trí tiếp tục có thể duyệt quá 50 phần tử của toàn bộ tập kết quả. Cơ chế này được trình bày trong [tài liệu Scrolling của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html).

Trong tình huống trên, kế hoạch hợp lý là yêu cầu lần lượt 50, 50 và 20 đơn. Sau lượt thứ ba, tác vụ dừng vì đã đạt 120, dù kho dữ liệu vẫn còn đơn phù hợp.

## 2. Giới hạn cố định bằng First và Top

`First` và `Top` là các từ khóa giới hạn trong phần chủ ngữ của derived query, trước `By`. Một số theo sau từ khóa biểu diễn giới hạn cố định. Danh sách từ khóa là abstraction chung; từng store có phạm vi hỗ trợ riêng. Xem [Repository query keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html).

Giả sử `PurchaseOrder` đã được ánh xạ trong ứng dụng và có các property:

| Property | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Mã đơn duy nhất |
| `status` | `String` | Trạng thái, chẳng hạn `PAID` |
| `createdAt` | `Instant` | Thời điểm tạo, có giá trị với mọi đơn trong ví dụ |

Repository cố định kích thước cửa sổ có thể được khai báo như sau khi module store hỗ trợ scroll query:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

public interface FixedPurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Window<PurchaseOrder> findFirst50ByStatusOrderByCreatedAtAscIdAsc(
            String status,
            ScrollPosition position);
}
```

Đọc tên phương thức theo từng phần:

- `findFirst50`: yêu cầu tối đa 50 phần tử của lượt đọc.
- `ByStatus`: lọc theo trạng thái được truyền vào.
- `OrderByCreatedAtAscIdAsc`: sắp xếp thời điểm tạo tăng dần, rồi đến mã đơn tăng dần.
- `ScrollPosition`: cung cấp mốc bắt đầu hoặc mốc tiếp tục.
- `Window<PurchaseOrder>`: trả nội dung cùng thông tin điều hướng.

Có thể thay `First50` bằng `Top50` cho cùng ý định giới hạn. Nếu bỏ con số, `First` hoặc `Top` mặc định giới hạn một kết quả; đây không phải cách khai báo một cửa sổ có kích thước tùy ý. Quy tắc về số mặc định được mô tả trong [Limiting Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.limit-query-result).

Giới hạn cố định phù hợp với một công việc có cấu hình ổn định, chẳng hạn mỗi lượt luôn đọc tối đa 50 đơn. Nếu mỗi yêu cầu cần một kích thước khác nhau, tạo nhiều phương thức chỉ khác `First20`, `First50`, `First100` sẽ làm repository khó mở rộng.

## 3. Giới hạn động bằng Limit

`org.springframework.data.domain.Limit` có từ Spring Data Commons 3.2. `Limit.of(n)` biểu diễn một giới hạn cụ thể; `Limit.unlimited()` biểu diễn không đặt giới hạn bằng abstraction này. Không dùng `null` để diễn đạt trạng thái không giới hạn. Xem [API Limit](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Limit.html).

Khai báo tương đương về mục tiêu đọc theo cửa sổ, nhưng nhận kích thước lúc gọi:

```java
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Window<PurchaseOrder> findByStatusOrderByCreatedAtAscIdAsc(
            String status,
            ScrollPosition position,
            Limit limit);
}
```

Ví dụ lấy lượt đầu:

```java
Window<PurchaseOrder> firstWindow =
        repository.findByStatusOrderByCreatedAtAscIdAsc(
                "PAID",
                ScrollPosition.offset(),
                Limit.of(50));
```

`Limit` là tham số điều khiển truy vấn, không phải một điều kiện so sánh với property tên `limit`. Không thêm `AndLimit` vào tên phương thức để biểu diễn kích thước cửa sổ.

Trong bài này, ứng dụng chọn quy ước `1 <= batchSize <= 500`. Đây là chính sách của service. Bản thân abstraction `Limit` không đặt một quy tắc dấu chung cho mọi ngữ cảnh; không nên dựa vào nó để xác thực kích thước cửa sổ cho ứng dụng. Với scrolling dữ liệu lớn, chủ động chọn một giới hạn hữu hạn thay vì truyền `Limit.unlimited()`.

## 4. Những tổ hợp cần khai báo rõ

Chỉ chọn một nguồn xác định giới hạn của một query method. Theo quy tắc query methods của Commons, không ghép `First`/`Top` với tham số `Limit`; cũng không ghép `Pageable` với `Limit`, vì `Pageable` đã mang kích thước trang. Tương tự, `Pageable` đã mang `Sort`. Xem [các tham số đặc biệt và tổ hợp không hợp lệ](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html).

```java
// Các chữ ký sau minh họa những tổ hợp không hợp lệ.

// Sai: hai cách khai báo giới hạn trong cùng query method.
Window<PurchaseOrder> findFirst50ByStatus(
        String status, ScrollPosition position, Limit limit);

// Sai: Pageable đã có kích thước trang.
List<PurchaseOrder> findByStatus(
        String status, Pageable pageable, Limit limit);

// Sai: Pageable đã chứa thông tin sắp xếp.
List<PurchaseOrder> findByStatus(
        String status, Pageable pageable, Sort sort);
```

Các chữ ký trên là ví dụ cần tránh, không phải phần bổ sung vào repository thực hành.

Nếu cần cả kích thước lẫn thứ tự động cho một scroll query, một dạng khai báo có thể dùng trong phạm vi store hỗ trợ là:

```java
Window<PurchaseOrder> findByStatus(
        String status,
        ScrollPosition position,
        Sort sort,
        Limit limit);
```

Ở dạng này, ứng dụng cần cố định giá trị `Sort` trong suốt lượt duyệt. Chẳng hạn, chọn `createdAt ASC, id ASC` khi bắt đầu rồi sử dụng cùng thứ tự đó cho các lần gọi tiếp theo. Mã hoàn chỉnh bên dưới dùng `OrderBy` trong tên phương thức để giữ ví dụ gọn và tránh thay đổi thứ tự giữa chừng.

Đừng suy ra một quy tắc chung rằng mọi loại giới hạn đều tự động được lấy giá trị nhỏ nhất. Quy tắc kết hợp `Top` với `Pageable` thuộc ngữ cảnh phân trang; không làm cho tổ hợp `Top` với `Limit` trở thành hợp lệ.

## 5. Đọc và sử dụng metadata của Window

`Window<T>` cho biết số phần tử, trạng thái rỗng, khả năng có cửa sổ tiếp theo và vị trí của một phần tử trong cửa sổ. `positionAt(index)` nhận chỉ số nằm trong cửa sổ hiện tại; không truyền số thứ tự trang hay chỉ số của toàn bộ tác vụ. Xem [API Window](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Window.html).

| Thao tác | Cách dùng trong vòng lặp |
| --- | --- |
| `window.isEmpty()` | Dừng trước khi tính chỉ số phần tử cuối |
| `window.size()` | Đếm số phần tử thực nhận |
| `window.hasNext()` | Xác định có nên yêu cầu cửa sổ tiếp theo |
| `window.positionAt(window.size() - 1)` | Lấy mốc sau phần tử cuối của cửa sổ đã xử lý |

Không dùng riêng điều kiện `window.size() == requested` để kết luận có dữ liệu tiếp. Một cửa sổ có thể vừa đủ kích thước nhưng cũng là cửa sổ cuối. Hãy sử dụng metadata điều hướng của kết quả.

`ScrollPosition.offset()` là vị trí khởi đầu cho offset scrolling, còn `ScrollPosition.keyset()` là vị trí khởi đầu cho keyset scrolling. Các đối tượng này phục vụ bắt đầu hoặc tiếp tục truy vấn, không phải hạn mức xử lý. Xem [API ScrollPosition](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ScrollPosition.html).

Trong scrolling, vị trí tiếp tục được hiểu theo nghĩa loại trừ phần tử tại mốc đó. Vì vậy, không thay `ScrollPosition.offset()` bằng `ScrollPosition.offset(0)` để diễn đạt lượt đầu: giá trị thứ hai đã trỏ vào phần tử ở offset 0, nên lượt đọc tiếp bắt đầu sau phần tử ấy. Quy tắc này được giải thích trong [Scrolling using Offset](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html#repositories.scrolling.offset).

## 6. Thực hành: đọc từng cửa sổ và giới hạn cả tác vụ

Service dưới đây sử dụng `PurchaseOrderRepository` ở mục 3. `PurchaseOrder` và cấu hình ánh xạ thuộc ứng dụng sử dụng store; phần service chỉ phụ thuộc các abstraction chung.

```java
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.data.domain.Limit;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public final class PurchaseOrderScroller {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderScroller(PurchaseOrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public long consumeAtMost(
            String status,
            int batchSize,
            long maximumItems,
            Consumer<PurchaseOrder> consumer) {

        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(consumer, "consumer");

        if (batchSize < 1 || batchSize > 500) {
            throw new IllegalArgumentException(
                    "batchSize must be between 1 and 500");
        }
        if (maximumItems < 0) {
            throw new IllegalArgumentException(
                    "maximumItems must not be negative");
        }

        ScrollPosition position = ScrollPosition.offset();
        long consumed = 0;

        while (consumed < maximumItems) {
            long remaining = maximumItems - consumed;
            int requested = (int) Math.min((long) batchSize, remaining);

            Window<PurchaseOrder> window =
                    repository.findByStatusOrderByCreatedAtAscIdAsc(
                            status, position, Limit.of(requested));

            if (window.isEmpty()) {
                break;
            }

            for (PurchaseOrder order : window) {
                consumer.accept(order);
                consumed++;
            }

            if (consumed == maximumItems || !window.hasNext()) {
                break;
            }

            position = window.positionAt(window.size() - 1);
        }

        return consumed;
    }
}
```

Các lựa chọn trong ví dụ phục vụ trực tiếp yêu cầu nghiệp vụ:

1. `maximumItems == 0` khiến vòng lặp không chạy, do đó không phát sinh truy vấn từ phương thức này.
2. `requested` là số nhỏ hơn giữa kích thước đợt và phần hạn mức còn lại.
3. Service đếm số phần tử thực nhận, thay vì cộng kích thước đã yêu cầu.
4. Chỉ tính vị trí cuối sau khi xác nhận cửa sổ có phần tử.
5. Service xử lý xong cửa sổ hiện tại rồi mới sử dụng vị trí cuối để đọc tiếp.
6. Không cộng offset thủ công; vị trí tiếp tục được lấy từ metadata trả về.

Giả sử có đúng 135 đơn phù hợp và dữ liệu không thay đổi trong ví dụ, lời gọi với `batchSize = 50` và `maximumItems = 120` có diễn tiến:

| Lượt | Đã xử lý trước lượt | Hạn mức còn lại | Limit gửi xuống | Số đơn nhận | Tổng đã xử lý |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 120 | 50 | 50 | 50 |
| 2 | 50 | 70 | 50 | 50 | 100 |
| 3 | 100 | 20 | 20 | 20 | 120 |

Sau lượt 3, `hasNext()` có thể vẫn là `true` vì còn 15 đơn, nhưng tác vụ đã hoàn thành hạn mức của mình. Dừng do hạn mức và dừng do hết dữ liệu là hai kết quả khác nhau.

Nếu nguồn dữ liệu chỉ có 73 đơn, service nhận lần lượt 50 và 23, rồi trả về 73. Nếu nguồn rỗng, service trả về 0. Các con số này là mô phỏng logic của ví dụ, không phải kết quả benchmark hoặc một lần chạy kiểm thử.

### Giới hạn đọc khác giới hạn xử lý

Một cách khác là luôn đọc 50 đơn rồi chỉ xử lý 20 đơn ở lượt cuối. Cách đó giữ được hạn mức xử lý nhưng đã đưa thêm dữ liệu về ứng dụng. Ví dụ trên chủ động thu nhỏ `Limit` của lượt cuối để tránh đưa về những đơn mà tác vụ không định sử dụng.

Nếu xử lý một phần cửa sổ rồi lưu checkpoint, checkpoint phải ứng với phần tử cuối đã xử lý thành công. Lưu vị trí cuối của cả cửa sổ trong trường hợp này có thể bỏ qua phần chưa xử lý khi tiếp tục.

Service minh họa không lưu checkpoint bền vững. Nếu `consumer.accept` ném lỗi, phương thức dừng và lỗi được truyền cho bên gọi. Để dùng trong một quy trình có khởi động lại, ứng dụng cần thiết kế ghi nhận tiến độ và hành vi xử lý lại theo yêu cầu nghiệp vụ; con số `Limit` không giải quyết việc đó.

### Khi nào dùng WindowIterator?

Khi muốn duyệt toàn bộ kết quả theo các cửa sổ có cấu hình ổn định, `WindowIterator` có thể giữ vị trí hiện tại và gọi hàm lấy cửa sổ tiếp theo giúp ứng dụng. Xem [API WindowIterator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/WindowIterator.html).

Với bài toán 50–50–20, vòng lặp tường minh giúp nhìn rõ cách cập nhật hạn mức còn lại. Nếu chỉ dừng một iterator sau 120 phần tử trong khi mỗi lượt luôn yêu cầu 50, lượt cuối có thể đã đọc thêm những phần tử chưa được sử dụng.

## 7. Sort, projection và loại vị trí vẫn phải phù hợp

Giảm `Limit` chỉ thay đổi kích thước lượt đọc. Nó không thay thế điều kiện để truy vấn tiếp tục đúng và hiệu quả.

Với keyset scrolling, các trường sắp xếp cần không null và phải có mặt trong kết quả để trích xuất vị trí tiếp tục. Projection thiếu các trường đó có thể gây lỗi. Chỉ mục phù hợp với thứ tự sắp xếp giúp khai thác cách đọc keyset. Offset sâu vẫn có chi phí bỏ qua dữ liệu dù cửa sổ nhỏ. Xem [Scrolling using Keyset-Filtering](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html#repositories.scrolling.keyset).

Trong ví dụ đơn hàng:

- Giữ nguyên bộ lọc `status = PAID` giữa các lượt.
- Giữ nguyên thứ tự `createdAt ASC, id ASC`.
- Khi thực hành projection với keyset, trả cả `createdAt` và `id`.
- Chỉ đổi số phần tử yêu cầu nếu cần điều chỉnh kích thước lượt đọc.

Dữ liệu thay đổi trong khi duyệt là một vấn đề riêng. Ví dụ, nếu tác vụ vừa đọc vừa đổi trạng thái từ `PAID` sang trạng thái khác, tập phù hợp sẽ co lại. Với offset scrolling, tiếp tục bỏ qua số phần tử cũ trên tập đã co có thể làm bỏ sót đơn. Với keyset, cập nhật trường tham gia sắp xếp cũng cần được phân tích cẩn thận. Đây là hệ quả của cách ứng dụng thay đổi tập dữ liệu, không phải một bảo đảm được cung cấp bởi `Limit`.

Vì vậy, trong bài thực hành hãy bắt đầu bằng dữ liệu cố định và một consumer chỉ đọc hoặc xuất dữ liệu. Khi chuyển sang xử lý cập nhật, xác định riêng yêu cầu nhất quán, chiến lược giao dịch và cách tiếp tục sau lỗi.

## 8. Hiểu đúng “trong phạm vi hỗ trợ”

Spring Data Commons cung cấp hợp đồng chung. Module store quyết định cách biến hợp đồng đó thành truy vấn hoặc thao tác với nguồn dữ liệu.

Trước khi áp dụng chữ ký trong bài vào dự án, xác định các điểm sau từ tài liệu đúng phiên bản của store:

| Khả năng | Điều cần xác nhận |
| --- | --- |
| Derived query có `First`/`Top` | Store hỗ trợ từ khóa và dạng trả về đang dùng |
| Tham số `Limit` | Phiên bản Commons có API này và module store xử lý được |
| Kết quả `Window<T>` | Hỗ trợ Scroll API cho loại query cụ thể |
| Loại vị trí | Hỗ trợ offset, keyset hoặc dạng phù hợp khác |
| Projection | Trả đủ dữ liệu để xây dựng metadata tiếp tục |
| Cơ chế khai báo query | Derived query, truy vấn chuỗi hay API fluent có thể có khả năng khác nhau |

Ví dụ cụ thể: tài liệu Spring Data JPA nêu Scroll API có thể dùng với query methods, Query by Example và Querydsl, đồng thời ghi nhận scrolling chưa được hỗ trợ cho string-based query methods và stored `@Procedure` query methods. Không chuyển tùy ý một ví dụ derived query trả `Window<T>` thành `@Query` và mặc định khả năng vẫn giống nhau. Xem [JPA — Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.scroll).

Nếu store chỉ hỗ trợ một truy vấn trả `List<T>` với `Limit`, kết quả đó tự nó chưa có metadata scroll. Cần chọn API phân trang/tiếp tục mà store hỗ trợ, hoặc xây dựng repository fragment có hợp đồng tiếp tục rõ ràng. Không tự dựng `Window` với `hasNext = true` chỉ vì danh sách vừa đủ kích thước: cần căn cứ xác định còn dữ liệu thực sự.

## 9. Chọn cách dùng theo nhu cầu

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Mỗi lượt đọc luôn cố định 50 đơn | Derived scroll query dùng `First50` hoặc `Top50` |
| Kích thước thay đổi giữa các lời gọi | Query method nhận `Limit`, nếu store hỗ trợ |
| Lần chạy có hạn mức riêng 120 đơn | Service theo dõi số đã xử lý và giới hạn lượt cuối |
| Cần thay đổi thứ tự trước khi bắt đầu lượt duyệt | Dùng `Sort` trong phạm vi hỗ trợ, rồi giữ nhất quán |
| Chỉ cần một nhóm kết quả, không tiếp tục | Truy vấn giới hạn trả kiểu phù hợp, chẳng hạn `List<T>` |
| Muốn duyệt toàn bộ tập theo đợt ổn định | Có thể dùng `WindowIterator` |

Các lựa chọn này giải quyết các yêu cầu khác nhau của cùng ví dụ. Cần mô tả rõ yêu cầu “50 phần tử mỗi lượt” hay “tối đa 50 phần tử cho cả tác vụ” trước khi thiết kế repository.

## 10. Bài thực hành tự kiểm tra

Dùng một tập dữ liệu cố định gồm 135 đơn `PAID`, có `createdAt` và `id` phù hợp với thứ tự đã chọn:

1. Dùng phương thức `First50` để lấy cửa sổ đầu, rồi lấy cửa sổ tiếp theo từ `positionAt` của đơn cuối.
2. Ghi lại mã các đơn đã đọc để quan sát sự khác nhau giữa giới hạn một lượt và tổng số đơn đã duyệt.
3. Dùng service với `batchSize = 50`, `maximumItems = 120`; giải thích vì sao lượt cuối yêu cầu 20.
4. Thay hạn mức bằng 0, rồi bằng 200; dự đoán số đơn xử lý trong mỗi trường hợp.
5. Thay nguồn dữ liệu bằng tập rỗng và tập có đúng 50 đơn; xác định vai trò của `isEmpty()` và `hasNext()`.
6. Giải thích vì sao không thêm `Limit` vào chữ ký đã có `First50`, và vì sao `offset(0)` không thay cho vị trí khởi đầu.
7. Với store đang dùng, xác định đúng loại query và loại scroll được hỗ trợ trước khi chuyển ví dụ sang projection hoặc truy vấn tự khai báo.

Kết quả cần đạt là một repository biểu đạt rõ cách giới hạn mỗi lượt và một service biểu đạt rõ điều kiện dừng của tác vụ. Metadata về vị trí tiếp tục phải gắn với chính bộ lọc, thứ tự và dữ liệu mà lượt duyệt đang sử dụng.