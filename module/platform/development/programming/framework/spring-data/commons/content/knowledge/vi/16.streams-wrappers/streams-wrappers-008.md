# Giới hạn bộ nhớ khi biến kết quả dạng luồng thành collection

Trong chương **Luồng và wrapper** của Spring Data Commons (`SPRING_DATA_COMMONS`), `Stream<T>` giúp diễn đạt việc duyệt kết quả truy vấn. Tuy nhiên, khi kết thúc bằng thao tác gom toàn bộ phần tử thành collection, ứng dụng vẫn phải giữ toàn bộ kết quả được gom trong bộ nhớ.

Vấn đề cần giải quyết là **bao nhiêu đối tượng còn được giữ lại cùng lúc**, ở tầng nào và trong bao lâu. Kiểu trả về có chữ “stream” không tự tạo một ngân sách heap cho nguồn dữ liệu, pipeline hoặc kết quả cuối.

Bài học trình bày cách ước lượng bộ nhớ, đặt giới hạn kết quả và xử lý từng batch. Ví dụ repository cụ thể dùng Spring Data JPA; khả năng streaming, projection và giới hạn truy vấn phải được đối chiếu với từng module store. Code sử dụng cú pháp Java 17, không ngụ ý mọi ứng dụng Spring Data đang dùng cùng phiên bản JDK.

## 1. Stream giảm cách duyệt, collection quyết định phần được giữ lại

Xét một nguồn trả các dòng phục vụ xuất dữ liệu:

```java
try (Stream<ExportRow> rows = repository.streamRows(tenantId)) {
    List<ExportRow> result = rows.toList();
    return result;
}
```

Dù nguồn có đọc tăng dần, `result` vẫn chứa tham chiếu tới tất cả các phần tử đã thu. Nếu trả một triệu dòng, một triệu đối tượng kết quả có thể phải sống ít nhất tới khi caller dùng xong list.

Một đường giữ tham chiếu điển hình:

```text
Caller
  -> List
      -> mảng hoặc cấu trúc lưu phần tử
          -> ExportRow
              -> các giá trị như String, Instant...
```

Garbage collector không thể thu hồi đối tượng chỉ vì nó đã được stream duyệt qua nếu list kết quả vẫn giữ đường tham chiếu tới đối tượng đó.

Nếu `N` là số phần tử được gom và kích thước trung bình mỗi phần tử được giữ là `R`, phần bộ nhớ kết quả thường tăng theo `O(N × R)`. Đây là mô hình dung lượng, không phải cam kết về layout đối tượng của một implementation.

`Stream.toList()` trả list không sửa được theo hợp đồng Java. Tính chất đó không giới hạn số phần tử hoặc số byte của kết quả. Xem [Java Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

## 2. Tách bốn loại giới hạn thường bị nhầm

| Giới hạn | Kiểm soát điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| Giới hạn kết quả ở query | Số dòng mà query được yêu cầu trả về. | Tổng bộ nhớ của object graph, các buffer và nhiều request đồng thời. |
| Fetch size của driver | Gợi ý cách lấy dữ liệu theo đợt ở tầng JDBC. | List cuối chỉ có từng ấy phần tử. |
| Kích thước batch của ứng dụng | Số phần tử ứng dụng gom trước khi chuyển cho bộ xử lý. | Bộ xử lý phía sau không giữ lại mọi batch. |
| Giới hạn collection đầu ra | Số phần tử được phép giữ trong kết quả của một lời gọi. | Mỗi phần tử có kích thước cố định hoặc đủ nhỏ. |

Theo [JDBC Statement.setFetchSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html#setFetchSize(int)), fetch size là một hint cho driver. Cách driver thực hiện còn phụ thuộc cấu hình và loại cơ sở dữ liệu.

Ví dụ nguồn trả 100.000 dòng, fetch size là 500 và cuối cùng gọi `toList()`. Nhiều đợt lấy dữ liệu vẫn có thể được cộng dồn thành list 100.000 phần tử.

Ngược lại, batch 500 dòng chỉ kiểm soát collection đang xử lý nếu các batch trước được giải phóng khỏi mọi nơi giữ tham chiếu.

## 3. Ước lượng ngân sách theo đối tượng còn sống

Một mô hình thực dụng cho một công việc đọc dữ liệu là:

```text
Bộ nhớ tăng thêm tại đỉnh
  ≈ đối tượng kết quả còn được giữ
  + cấu trúc collection và phần dung lượng dư
  + dữ liệu nguồn hoặc persistence context chưa tính ở trên
  + hàng đợi và buffer đầu ra
  + cấu trúc trung gian, bản sao tạm thời
```

Khi một entity vừa có trong list vừa có trong persistence context, không cộng kích thước cùng một đối tượng hai lần. Điều cần cộng thêm là các đối tượng hoặc metadata khác thực sự còn sống.

Giả sử phần object graph riêng của mỗi dòng chiếm trung bình **1 KiB**, chưa tính ô tham chiếu trong list. Đây là số liệu giả định để tính toán:

| Số dòng | Chỉ riêng object graph của các dòng |
| ---: | ---: |
| 10.000 | Khoảng 9,8 MiB. |
| 100.000 | Khoảng 97,7 MiB. |
| 1.000.000 | Khoảng 976,6 MiB. |

Trong bảng, `1 KiB = 1.024 byte`, `1 MiB = 1.048.576 byte`. Nếu giả định thêm mỗi ô tham chiếu là 8 byte, một triệu ô cần khoảng 7,6 MiB nữa. Kích thước tham chiếu thực tế phụ thuộc JVM và cấu hình; không dùng số giả định này như một hằng số của Java.

Ứng dụng còn cần heap cho request khác, cache và các đối tượng đang xử lý. Nếu tổng heap là 256 MiB, điều đó không có nghĩa một request xuất dữ liệu được dùng trọn 256 MiB.

Có thể chọn giới hạn số dòng ban đầu bằng:

```text
maxRows sơ bộ
  ≤ ngân sách dành cho kết quả
    / chi phí ước lượng cho mỗi dòng
```

Sau đó phải điều chỉnh theo phần tử lớn, overhead và số công việc đồng thời. Một trường văn bản dài bất thường có thể làm giả định trung bình mất tác dụng.

## 4. Chọn dữ liệu đầu ra trước khi chọn collector

Giả sử entity JPA `AuditEvent` đã được mapping với `id`, `tenantId`, `createdAt`, `action` và một trường nội dung lớn khác. Bản xuất chỉ cần ba trường đầu ra:

```java
package example.audit;

import java.time.Instant;

public record ExportRow(
    Long id,
    Instant createdAt,
    String action
) {}
```

Một repository JPA có thể khai báo query DTO tường minh:

```java
package example.audit;

import java.util.stream.Stream;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface AuditExportRepository
        extends Repository<AuditEvent, Long> {

    @Query("""
        select new example.audit.ExportRow(
            e.id, e.createdAt, e.action
        )
        from AuditEvent e
        where e.tenantId = :tenantId
        order by e.id
        """)
    Stream<ExportRow> streamRows(
        @Param("tenantId") String tenantId
    );
}
```

Đây là JPQL và annotation của Spring Data JPA. Constructor expression dùng tên đầy đủ của DTO và constructor phù hợp. Các cấu hình entity, repository scanning và transaction manager được giả định đã có.

Projection lựa chọn trường cần dùng thay vì yêu cầu toàn bộ aggregate. Xem [Spring Data JPA: Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html).

Trong ví dụ, DTO không giữ tham chiếu tới entity hoặc trường nội dung lớn đã loại khỏi query. Tuy nhiên, `action` vẫn có kích thước thay đổi. Một triệu DTO nhỏ vẫn có thể vượt ngân sách nếu bị gom vào một list duy nhất.

## 5. Thu collection có giới hạn và báo rõ khi vượt mức

Có hai hợp đồng khác nhau:

- **Lấy tối đa K dòng:** trả một phần kết quả theo quy tắc đã công bố.
- **Chỉ trả kết quả đầy đủ nếu không quá K dòng:** nếu vượt K, báo lỗi hoặc yêu cầu đổi cách lấy dữ liệu.

Không dùng `limit(K)` rồi trả kết quả như thể đó là toàn bộ dữ liệu khi caller yêu cầu hợp đồng thứ hai.

Helper dưới đây thực hiện hợp đồng “đầy đủ hoặc báo vượt giới hạn”. Helper không đóng stream; caller sở hữu nguồn và phải đóng nó.

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public final class BoundedStreams {

    private BoundedStreams() {}

    public static <T> List<T> collectAtMost(
        Stream<? extends T> source,
        int maxRows
    ) {
        Objects.requireNonNull(source, "source");

        if (maxRows <= 0) {
            throw new IllegalArgumentException(
                "maxRows must be positive"
            );
        }

        List<T> result = new ArrayList<>(
            Math.min(maxRows, 256)
        );
        Iterator<? extends T> iterator = source.iterator();

        while (iterator.hasNext()) {
            if (result.size() == maxRows) {
                throw new ResultLimitExceededException(maxRows);
            }

            result.add(iterator.next());
        }

        return result;
    }

    public static final class ResultLimitExceededException
            extends RuntimeException {

        public ResultLimitExceededException(int maxRows) {
            super("Result exceeds " + maxRows + " rows");
        }
    }
}
```

Hành vi của thuật toán:

| Số phần tử nguồn | Kết quả |
| --- | --- |
| Nhỏ hơn K | Trả đầy đủ các phần tử. |
| Bằng K | Kiểm tra nguồn đã hết rồi trả list K phần tử. |
| Lớn hơn K | Khi biết còn phần tử sau K dòng đã giữ, ném lỗi. |

List trong helper không chứa hơn K phần tử. Việc `hasNext()` kiểm tra còn phần tử có thể khiến nguồn lấy thêm dữ liệu hoặc giữ buffer riêng; giới hạn của list không phải giới hạn mọi tầng nguồn.

Helper còn phụ thuộc pipeline đầu vào. Nếu caller truyền `source.sorted(...)`, việc tạo iterator không loại bỏ bộ nhớ mà phép sắp xếp cần trong lúc duyệt.

### Đặt giới hạn tại service

Ví dụ sau sử dụng DTO và repository ở phần trước; helper được đặt trong package có thể import tương ứng:

```java
import java.util.List;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditExportService {

    private static final int MAX_ROWS_IN_RESPONSE = 5_000;

    private final AuditExportRepository repository;

    public AuditExportService(AuditExportRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<ExportRow> loadSmallExport(String tenantId) {
        try (Stream<ExportRow> rows =
                 repository.streamRows(tenantId)) {

            return BoundedStreams.collectAtMost(
                rows,
                MAX_ROWS_IN_RESPONSE
            );
        }
    }
}
```

Giới hạn 5.000 là ví dụ về chính sách phía service, không phải giá trị chung nên dùng cho mọi hệ thống. Không cho caller tùy ý chọn một mức rất lớn rồi coi helper đã bảo vệ ngân sách.

Nếu vượt giới hạn, stream được đóng khi rời khối `try`. Method không âm thầm trả 5.000 dòng đầu như một bản xuất đầy đủ.

Giới hạn này kiểm soát số đối tượng trong kết quả. Muốn có ngân sách byte chặt hơn còn phải kiểm soát kích thước trường, payload lớn và overhead thực tế.

## 6. Không dùng một collection đã đầy để kiểm tra giới hạn

Thiết kế sau kiểm tra quá muộn:

```java
List<ExportRow> result = rows.toList();

if (result.size() > maxRows) {
    throw new IllegalStateException("Too many rows");
}
```

Tất cả phần tử đã được gom trước khi kiểm tra chạy. Nếu quá trình gom không đủ bộ nhớ, điều kiện phía sau không có cơ hội thực hiện.

Một query đếm trước cũng không tự bảo đảm an toàn: dữ liệu có thể thay đổi giữa lần đếm và lần lấy, và số dòng không phản ánh kích thước từng dòng. Việc đếm có thể phục vụ nghiệp vụ nhưng vẫn cần giới hạn ngay tại nơi tích lũy.

Khi module hỗ trợ, có thể yêu cầu query trả tối đa K + 1 dòng để phát hiện còn phần vượt K. Cần giữ cùng bộ lọc, thứ tự và hợp đồng kết quả; cách biểu diễn giới hạn thuộc khả năng của store. Với số nguyên giới hạn, cũng phải tránh tràn khi tính K + 1.

Giới hạn tại query giúp tránh yêu cầu kết quả quá lớn từ nguồn. Giới hạn tại tầng gom bảo vệ hợp đồng của collection đầu ra. Hai vị trí giải quyết hai phần khác nhau của công việc.

## 7. Pipeline có thể giữ dữ liệu trước terminal operation

Không phải mọi pipeline đều chỉ giữ một phần tử tại một thời điểm.

| Pipeline hoặc collector | Dữ liệu có thể phải giữ |
| --- | --- |
| `map(...)` không có lưu trữ bên ngoài | Các giá trị đang xử lý và buffer của nguồn. |
| `toList()`, `collect(toList())` | Các phần tử đầu ra đã gom. |
| `toSet()`, `distinct()` | Thông tin về các giá trị phân biệt. |
| `groupingBy(key)` với list mặc định | Toàn bộ phần tử trong các nhóm. |
| `groupingBy(key, counting())` | Một trạng thái đếm cho mỗi khóa. |
| `joining()` | Nội dung chuỗi đầu ra được tích lũy. |
| `sorted()` trên nguồn chưa có thứ tự cần thiết | Có thể phải đệm dữ liệu để sắp xếp. |

Các dạng reduction và nhóm được mô tả trong [Java Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).

Ví dụ:

```java
List<ExportRow> firstRows = rows
    .sorted(Comparator.comparing(ExportRow::createdAt))
    .limit(100)
    .toList();
```

Kết quả cuối chỉ có tối đa 100 dòng, nhưng trên một nguồn chưa được sắp theo thời gian, phép `sorted` vẫn có thể phải xử lý và đệm toàn bộ dữ liệu.

Đảo thành `limit(100).sorted(...)` thay đổi ý nghĩa: chỉ sắp xếp 100 phần tử đã lấy trước, thay vì tìm 100 phần tử đứng đầu theo thời gian trên toàn tập.

Khi yêu cầu là top K theo một thứ tự, hãy cân nhắc biểu diễn sắp xếp và giới hạn ngay trong query có hỗ trợ. Nếu buộc xử lý ở ứng dụng, một cấu trúc top K có giới hạn có thể phù hợp hơn sắp toàn bộ; phải giữ đúng comparator và quy tắc xử lý trường hợp bằng nhau.

Tương tự, đếm theo một khóa gần như duy nhất cho mỗi dòng vẫn có thể làm số nhóm tăng theo N. Đổi list thành map không tự tạo giới hạn dung lượng.

## 8. Xử lý theo batch để không giữ toàn bộ đầu ra

Nếu bộ nhận dữ liệu có thể xử lý từng phần, ứng dụng có thể gom tối đa B dòng, chuyển batch đi, rồi bỏ tham chiếu tới batch đó.

```text
Nguồn
  -> batch 1: xử lý xong và giải phóng
  -> batch 2: xử lý xong và giải phóng
  -> ...
  -> batch cuối
```

Method sau có thể đặt trong helper `BoundedStreams`, cùng các import đã có và thêm `java.util.function.Consumer`:

```java
public static <T> long forEachBatch(
    Stream<? extends T> source,
    int batchSize,
    Consumer<List<T>> sink
) {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(sink, "sink");

    if (batchSize <= 0) {
        throw new IllegalArgumentException(
            "batchSize must be positive"
        );
    }

    Iterator<? extends T> iterator = source.iterator();
    List<T> batch = new ArrayList<>(
        Math.min(batchSize, 256)
    );
    long processed = 0;

    while (iterator.hasNext()) {
        batch.add(iterator.next());

        if (batch.size() == batchSize) {
            int delivered = batch.size();
            sink.accept(batch);
            processed += delivered;

            batch = new ArrayList<>(
                Math.min(batchSize, 256)
            );
        }
    }

    if (!batch.isEmpty()) {
        int delivered = batch.size();
        sink.accept(batch);
        processed += delivered;
    }

    return processed;
}
```

Hợp đồng của `sink` trong ví dụ:

- Chạy đồng bộ và xử lý xong batch trước khi trả về.
- Không sửa nội dung batch và không giữ tham chiếu tới batch hoặc các dòng để tích lũy vô hạn.
- Nếu thất bại, truyền lỗi về caller; không giả vờ rằng batch đã hoàn tất.

Helper không đóng nguồn. Service tiếp tục dùng `try-with-resources` và phạm vi giao dịch phù hợp khi gọi nó:

```java
// Phần thân của một method service chạy trong giao dịch đọc.
// sink có kiểu Consumer<List<ExportRow>>.
try (Stream<ExportRow> rows = repository.streamRows(tenantId)) {
    long processed = BoundedStreams.forEachBatch(
        rows,
        500,
        sink
    );

    return processed;
}
```

Với 1.201 dòng và B = 500, các batch có kích thước 500, 500 và 201. Helper không tạo một list 1.201 dòng.

Đây là giới hạn bộ đệm tại ứng dụng. Nó chỉ dẫn tới mức giữ dữ liệu gần `O(B × R)` cho phần batch nếu nguồn, sink và các tầng khác cũng giữ dữ liệu có giới hạn.

Số đếm chỉ được trả khi method hoàn tất bình thường. Nếu sink lỗi sau khi đã tạo một phần tác động, chính sách retry và checkpoint vẫn thuộc nghiệp vụ.

## 9. Những cách vô tình giữ lại toàn bộ batch

Batching không còn đạt mục tiêu nếu sink làm việc này:

```java
List<List<ExportRow>> allBatches = new ArrayList<>();

// Mỗi batch được giữ lại trong một danh sách lớn hơn.
BoundedStreams.forEachBatch(rows, 500, allBatches::add);
```

Tổng số dòng còn được giữ vẫn tăng theo N.

Một hàng đợi tác vụ không giới hạn cũng tạo kết quả tương tự nếu nguồn đọc nhanh hơn consumer xử lý. Ví dụ producer tạo 100 batch mỗi giây, consumer xử lý được 20 batch mỗi giây; số batch chờ tăng khoảng 80 mỗi giây khi tải đó tiếp tục.

Để giữ giới hạn, cần xác định:

| Vị trí | Giới hạn cần có |
| --- | --- |
| Batch đang tạo | Tối đa B dòng hoặc chính sách dung lượng tương ứng. |
| Hàng đợi giữa producer và consumer | Số batch hoặc dung lượng tối đa. |
| Consumer đang chạy | Số tác vụ đồng thời. |
| Bộ đệm ghi file hoặc response | Chính sách ghi tăng dần, không tích lũy toàn bộ nội dung. |

Nếu có Q batch chờ và W consumer, phần dữ liệu của đường xử lý có thể gần:

```text
(Batch đang tạo + Q batch chờ + W batch đang xử lý)
    × số dòng mỗi batch
    × chi phí mỗi dòng
```

Đây là mô hình ước lượng cho các batch độc lập, không phải công thức layout chính xác. Cần cộng thêm nguồn và overhead.

Một thư viện ghi dữ liệu vào `ByteArrayOutputStream` rồi chỉ xuất một lần ở cuối vẫn có thể giữ toàn bộ bản xuất. Chuyển list lớn thành một mảng byte lớn không loại bỏ vấn đề dung lượng.

## 10. Streamable, wrapper và persistence context

### Wrapper không thay đổi ngân sách của dữ liệu bên dưới

`Streamable<T>` là abstraction tiện dụng trên `Iterable`, cung cấp cách tạo stream và chuyển thành collection. API `toList()` tạo list không sửa được. Xem [Spring Data Streamable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/util/Streamable.html).

Nếu `Streamable` hoặc một wrapper nghiệp vụ đang bao một collection đã có sẵn, việc gọi `stream()` không hoàn tác bộ nhớ collection đó đã dùng.

Các tình huống cần nhận diện:

```java
// Nếu findAll đã lấy đầy đủ kết quả thành List,
// stream ở đây chỉ duyệt dữ liệu đã có trong bộ nhớ.
List<AuditEvent> events = repositoryWithList.findAll();
Stream<AuditEvent> eventsStream = events.stream();
```

Trong đoạn trên, `repositoryWithList` biểu diễn một repository có method `findAll()` trả list. Đây không phải thay đổi đối với `AuditExportRepository` đã khai báo.

Tương tự, gọi `toList()` bên trong một wrapper để “tiện dùng lại” có thể biến một nguồn có thể duyệt thành dữ liệu được giữ dài hạn. Cần quyết định rõ wrapper biểu diễn nguồn, một batch hay toàn bộ kết quả.

### Managed entity có thể được giữ ngoài collection của ứng dụng

Với Hibernate, persistence context giữ tham chiếu mạnh tới các managed entity. Xem [Hibernate Session](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/Session.html).

Do đó, một vòng lặp entity với batch nhỏ vẫn có thể làm bộ nhớ tăng nếu session giữ các entity của mọi batch đã đọc. `@Transactional(readOnly = true)` không có nghĩa mỗi entity tự được detach sau khi consumer chạy xong.

Trong một bản xuất chỉ cần giá trị, DTO projection như ví dụ có thể tránh việc đầu ra chứa managed entity. Nếu vẫn cần entity, phải thiết kế vòng đời persistence context, giao dịch và việc detach theo use case; không chèn `clear()` tùy tiện khi còn thay đổi đang chờ ghi.

Những đặc điểm trên thuộc JPA/Hibernate. Không áp đặt persistence context hoặc cùng cách giải phóng entity cho mọi kho dữ liệu sử dụng Spring Data Commons.

## 11. Bộ nhớ đỉnh còn bao gồm bản sao và nhiều request

Một list có thể có capacity lớn hơn size. Với `ArrayList`, dung lượng tự tăng và chi tiết chính sách tăng không được API cố định cho mọi implementation. Xem [Java ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Trong lúc mở rộng, chuyển dạng dữ liệu hoặc serialize, bộ nhớ đỉnh có thể cao hơn kích thước kết quả ổn định. Không coi số byte của file đầu ra là số byte heap chính xác.

Một bản sao collection thường sao chép các tham chiếu, không mặc nhiên sao chép sâu từng DTO. Dù vậy, mảng hoặc cấu trúc tham chiếu mới và các buffer trung gian vẫn cần bộ nhớ.

Cũng phải xét tải đồng thời. Nếu mỗi công việc đang giữ khoảng 30 MiB và có 12 công việc chạy cùng lúc, riêng phần đó đã khoảng 360 MiB, trước khi cộng heap nền.

Vì vậy, ngân sách cần gắn với cả:

- Số dòng và kích thước mỗi kết quả.
- Số công việc được xử lý đồng thời.
- Thời gian giữ kết quả trước khi giải phóng.
- Bộ đệm ở các bước chuyển đổi và đầu ra.

Tăng heap chỉ thay đổi dung lượng sẵn có. Nếu hợp đồng vẫn cho phép giữ kết quả tăng không giới hạn, một tập dữ liệu lớn hơn có thể lại vượt ngân sách.

## 12. Chọn cấu trúc theo kết quả caller thực sự cần

| Caller cần gì? | Cách biểu diễn nên cân nhắc |
| --- | --- |
| Một con số tổng hợp | Query tổng hợp hoặc reduction chỉ giữ trạng thái cần thiết. |
| Một danh sách nhỏ, đầy đủ | Giới hạn phía query khi có hỗ trợ và kiểm tra ngay trong quá trình thu. |
| Một trang giao diện | Trả đúng một trang hoặc slice theo khả năng module. |
| Xuất toàn bộ dữ liệu lớn | Đọc và ghi tăng dần, batch có giới hạn, không gom mọi dòng. |
| Top K theo thứ tự | Sắp xếp và giới hạn tại nguồn hoặc thuật toán top K phù hợp. |
| Kết quả có thể duyệt lại nhiều lần | Xác định rõ nơi lưu, dung lượng và thời gian sống; có thể cần lưu ngoài heap. |

Không gom mọi `Page`, `Slice` hoặc `Window` vào một list lớn rồi coi việc phân trang đã giới hạn tổng bộ nhớ.

Spring Data Commons định nghĩa các hợp đồng dùng chung; module store quyết định cách truy vấn và hỗ trợ streaming cụ thể. Stream có thể giữ tài nguyên của store nên phải được đóng đúng vòng đời. Xem [Spring Data Commons: Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-streaming).

Đối với kết quả rất lớn cần đọc lại, có thể thiết kế một bản xuất được lưu thành file hoặc đối tượng lưu trữ rồi trả định danh bản xuất. Khi đó vẫn phải ghi tăng dần và quản lý thời gian sống của tài nguyên lưu trữ.

## 13. Thực hành xác định phần đang giữ bộ nhớ

Hãy phân tích các biến thể sau mà không đồng nhất chúng chỉ vì đều có chữ `stream`:

1. Nguồn tăng dần rồi `toList()`.
2. Nguồn tăng dần, xử lý đồng bộ từng batch 500 và không giữ batch cũ.
3. Batch 500 nhưng thêm từng batch vào một list tổng.
4. `groupingBy(action, counting())` với vài giá trị action.
5. Đổi khóa nhóm thành một ID gần như duy nhất.
6. `sorted(...).limit(100).toList()` trên nguồn chưa được sắp theo comparator.
7. List DTO có tối đa 5.000 dòng nhưng một trường có thể chứa văn bản rất lớn.

Với mỗi biến thể, chỉ ra đường giữ tham chiếu và biến nào làm dung lượng tăng: tổng số dòng N, số khóa phân biệt D, kích thước batch B hay kích thước từng phần tử R.

Các tình huống kiểm tra hợp đồng của helper:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Nguồn rỗng | Collection rỗng; batching không gọi sink. |
| Nguồn đúng K dòng | `collectAtMost` trả đầy đủ K dòng. |
| Nguồn K + 1 dòng | Báo vượt giới hạn, không trả kết quả bị cắt như kết quả đầy đủ. |
| 1.201 dòng, batch 500 | Ba lần xử lý với kích thước 500, 500, 201. |
| Sink lỗi ở batch thứ hai | Nguồn vẫn cần được đóng; không có kết quả hoàn tất giả. |
| Nhiều lượt xuất đồng thời | Ngân sách tổng phải tính cả các lượt đang chạy. |

Khi đánh giá dung lượng trong môi trường thực tế, dùng dữ liệu có kích thước trường và số khóa gần tải thật. Đo cả bộ nhớ đỉnh, các đối tượng còn được giữ, tốc độ cấp phát và hành vi GC. Dữ liệu mô phỏng dùng chung một chuỗi ngắn cho mọi dòng không đại diện cho tập dữ liệu gồm các chuỗi dài khác nhau.

Một chính sách bộ nhớ có thể kiểm chứng cần nêu rõ giới hạn ở nguồn, nơi tích lũy, hàng đợi và đầu ra. Chuyển sang collection là quyết định giữ dữ liệu; hãy thực hiện quyết định đó với dung lượng và hợp đồng kết quả đã được xác định.
