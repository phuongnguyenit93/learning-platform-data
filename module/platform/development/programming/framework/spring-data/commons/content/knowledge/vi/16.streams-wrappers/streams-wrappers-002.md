# Đóng Stream bằng try-with-resources

## 1. Vì sao một luồng truy vấn cần được đóng?

Trong Spring Data, một query method có thể trả về `Stream<T>` để ứng dụng tiêu thụ kết quả theo một pipeline Java. Tùy mô-đun kho dữ liệu và cách triển khai truy vấn, luồng có thể gắn với cursor, kết quả JDBC, session hoặc tài nguyên truy cập dữ liệu khác. Vòng đời của các tài nguyên đó có thể kéo dài sau khi phương thức repository đã trả về.

Vì vậy, việc nhận được một đối tượng `Stream` chưa có nghĩa là truy vấn đã hoàn tất về mặt quản lý tài nguyên. Người gọi phải xác định nơi tiêu thụ và nơi đóng luồng.

Mẫu sử dụng cơ bản là:

```java
try (Stream<PurchaseOrder> orders = repository.findByStatus(status)) {
    orders.forEach(this::handle);
}
```

`try-with-resources` bảo đảm gọi `close()` khi rời khối `try` trong luồng thực thi Java thông thường, kể cả khi xử lý ném exception hoặc kết thúc sớm. Đây là bảo đảm về vòng đời tài nguyên; nó không tự bảo đảm dữ liệu được xử lý đúng một lần.

Trong phạm vi **SPRING_DATA_COMMONS**, `Stream` là kiểu của Java được tích hợp vào abstraction repository. Commons không áp đặt rằng mọi kho dữ liệu đều hỗ trợ query method trả `Stream`, cũng không áp đặt cách driver lấy dữ liệu. Các ví dụ dưới đây giả định mô-đun và phiên bản sử dụng có hỗ trợ kiểu kết quả đó.

## 2. Hiểu đúng hợp đồng của Stream

`java.util.stream.Stream<T>` kế thừa `BaseStream`, và `BaseStream` kế thừa `AutoCloseable`. Vì vậy một `Stream` có thể được khai báo trong danh sách tài nguyên của `try-with-resources`.

Có hai trách nhiệm khác nhau:

| Trách nhiệm | Ví dụ | Tác dụng |
| --- | --- | --- |
| Tiêu thụ pipeline | `forEach`, `count`, `collect`, `findFirst` | Yêu cầu pipeline thực hiện phép tính hoặc lấy kết quả |
| Đóng pipeline | `close()` | Chạy các close handler được gắn với luồng và giải phóng tài nguyên theo triển khai |

Một terminal operation **không tự gọi `close()`**. Tiêu thụ hết phần tử cũng không thay thế việc đóng luồng theo hợp đồng của API.

Điều này dễ bị bỏ qua khi đã quen với các luồng tạo từ dữ liệu trong bộ nhớ:

```java
List<String> names = Arrays.asList("An", "Bình", "Chi");
long count = names.stream().filter(name -> name.length() > 2).count();
```

Luồng từ một `List` thông thường không giữ cursor cơ sở dữ liệu cần đóng. Nhưng cùng một kiểu khai báo `Stream<T>` có thể đại diện cho kết quả truy vấn đang giữ tài nguyên. Không suy ra cách quản lý tài nguyên chỉ từ tên phương thức terminal.

Với luồng kết quả do repository cung cấp, nên đặt vòng đời rõ ràng bằng `try-with-resources` ngay tại nơi nhận và tiêu thụ luồng.

## 3. Cú pháp và thứ tự thực thi

```java
import java.util.stream.Stream;

try (Stream<PurchaseOrder> orders = repository.findByStatus(status)) {
    orders.filter(PurchaseOrder::isExportable)
          .forEach(this::handle);
}
```

Các bước diễn ra theo thứ tự:

1. Gọi repository để lấy luồng.
2. Nếu lấy luồng thành công, đăng ký nó làm tài nguyên của khối `try`.
3. Thực hiện pipeline trong thân khối.
4. Gọi `orders.close()` khi rời khối.
5. Tiếp tục thực thi sau khối, hoặc truyền exception ra ngoài.

Nếu chính lời gọi repository ném exception trước khi trả về luồng, chưa có tài nguyên `orders` được khởi tạo thành công để khối `try` đóng. Việc giải phóng những tài nguyên mà repository đã mở nhưng chưa chuyển giao thuộc trách nhiệm của triển khai đó.

`try-with-resources` có từ Java 7; Stream API có từ Java 8. Cách khai báo tài nguyên ngay trong ngoặc như trên dùng được với Stream từ Java 8. Các phiên bản Java mới hơn còn cho phép tham chiếu biến tài nguyên đã khai báo, nếu biến đáp ứng yêu cầu final hoặc effectively final. Dù dùng cú pháp nào, điều quan trọng vẫn là phạm vi sống của luồng.

### 3.1. Pipeline trung gian vẫn thuộc cùng vòng đời

Các bước như `filter`, `map` và `peek` tạo pipeline nhưng chưa phải thao tác terminal:

```java
try (Stream<PurchaseOrder> orders = repository.findByStatus(status)) {
    orders.filter(PurchaseOrder::isExportable)
          .map(PurchaseOrder::getId)
          .forEach(System.out::println);
}
```

Đóng luồng gốc đã đăng ký trong `try` sẽ đóng pipeline liên quan theo hợp đồng của Stream. Không cần khai báo từng kết quả của `filter` hoặc `map` thành một tài nguyên riêng chỉ để đóng lặp lại.

Nếu pipeline tạo ra một luồng độc lập khác hoặc mở thêm một tài nguyên bên ngoài, tài nguyên mới đó vẫn cần hợp đồng sở hữu riêng. Không giả định rằng mọi tài nguyên được mở bên trong lambda đều tự động thuộc vòng đời của luồng gốc.

## 4. Ví dụ repository và service có phạm vi transaction rõ ràng

Giả sử ứng dụng có kiểu dữ liệu `PurchaseOrder` đã được mapping bởi mô-đun kho dữ liệu, với ba thuộc tính:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh đã được cấp cho đơn hàng được truy vấn |
| `status` | `String` | Trạng thái, ví dụ `PENDING` |
| `createdAt` | `Instant` | Thời điểm tạo đơn hàng |

Repository sử dụng một derived query có thứ tự rõ ràng:

```java
import java.time.Instant;
import java.util.stream.Stream;

import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Stream<PurchaseOrder>
    findByStatusAndCreatedAtBeforeOrderByIdAsc(
            String status,
            Instant cutoff);
}
```

Đây là hợp đồng repository minh họa. Entity mapping, dependency và khả năng thực thi query dạng stream phải được cấu hình theo mô-đun cụ thể. Tên phương thức không làm cho một mô-đun vốn không hỗ trợ streaming tự có khả năng đó.

Service tiêu thụ toàn bộ luồng trong một lời gọi đồng bộ:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.function.LongConsumer;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PendingOrderReader {

    private final PurchaseOrderRepository repository;

    public PendingOrderReader(PurchaseOrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    @Transactional(readOnly = true)
    public void visitIds(Instant cutoff, LongConsumer consumer) {
        Objects.requireNonNull(cutoff, "cutoff");
        Objects.requireNonNull(consumer, "consumer");

        try (Stream<PurchaseOrder> orders =
                repository.findByStatusAndCreatedAtBeforeOrderByIdAsc(
                        "PENDING", cutoff)) {

            orders.mapToLong(PurchaseOrder::getId)
                  .forEachOrdered(consumer);
        }
    }
}
```

Ví dụ giả định các đơn hàng đã lưu có `id` khác `null`. `mapToLong` tạo pipeline `LongStream`, còn luồng gốc vẫn là tài nguyên được đóng ở cuối khối.

Với cách quản lý transaction thông thường qua Spring proxy, lời gọi phải đi qua bean proxy có cấu hình transaction hoạt động. Khi đó phạm vi xử lý mong muốn là:

```text
Bắt đầu transaction
  Lấy Stream từ repository
    Duyệt kết quả
    Gọi consumer đồng bộ
  Đóng Stream khi rời try
Kết thúc phương thức service
Hoàn tất transaction
```

`try-with-resources` và transaction giải quyết hai vấn đề liên quan nhưng khác nhau. Khối `try` quản lý vòng đời luồng; transaction cung cấp ngữ cảnh truy cập dữ liệu cần thiết theo mô-đun. Một số mô-đun hoặc dạng truy vấn streaming yêu cầu transaction còn hoạt động trong lúc duyệt.

`readOnly = true` thể hiện ý định đọc và có thể được hạ tầng dùng để tối ưu theo triển khai. Nó không tự cung cấp snapshot bất biến, không tự giới hạn bộ nhớ, cũng không tự tạo cơ chế cursor ở phía driver.

Không mặc định rằng việc một phương thức nằm cùng lớp với phương thức có annotation đã kích hoạt transaction. Trong mô hình Spring proxy thông thường, self-invocation có thể không đi qua transaction interceptor.

### 4.1. Đóng Stream chưa chắc trả connection về pool ngay

Việc đóng luồng có thể giải phóng cursor hoặc tài nguyên kết quả truy vấn. Tuy nhiên, connection có thể vẫn gắn với transaction và chỉ được trả về pool khi transaction kết thúc.

Vì thế không diễn giải `close()` thành lời hứa rằng mọi tài nguyên liên quan đến toàn bộ transaction đều biến mất ngay tại cuối khối `try`. Cần phân biệt vòng đời kết quả truy vấn với vòng đời transaction và connection.

## 5. Terminal operation không thay cho close

Các mẫu sau đều cần vòng đời tài nguyên rõ ràng nếu nguồn là luồng truy vấn:

| Pipeline | Tính chất tiêu thụ | Có tự đóng Stream không? |
| --- | --- | --- |
| `forEach(...)` | Thường duyệt toàn bộ | Không |
| `count()` | Tính kết quả theo pipeline | Không |
| `collect(...)` | Gom kết quả | Không |
| `findFirst()` | Có thể kết thúc sớm | Không |
| `anyMatch(...)` | Có thể kết thúc sớm | Không |
| `limit(10).collect(...)` | Chỉ cần một phần kết quả | Không |

Ở các phiên bản Java có `Stream.toList()`, quy tắc tương tự vẫn áp dụng: lấy được `List` không có nghĩa là terminal operation đã gọi `close()` cho luồng nguồn.

Một ví dụ dễ gây hiểu lầm:

```java
// Thiếu phạm vi đóng luồng nguồn.
List<Long> ids = repository.findByStatus("PENDING")
        .map(PurchaseOrder::getId)
        .collect(Collectors.toList());
```

Cách viết có quản lý tài nguyên:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Long> ids;

try (Stream<PurchaseOrder> orders = repository.findByStatus("PENDING")) {
    ids = orders.map(PurchaseOrder::getId)
                .collect(Collectors.toList());
}
```

Các đoạn dùng `findByStatus` giả định repository có thêm khai báo tương ứng:

```java
Stream<PurchaseOrder> findByStatus(String status);
```

Gom toàn bộ dữ liệu vào `List` vẫn tiêu thụ bộ nhớ theo số kết quả. `try-with-resources` khắc phục vòng đời tài nguyên, không biến việc gom dữ liệu thành thao tác có bộ nhớ hằng số.

## 6. Kết thúc sớm vẫn phải đóng luồng

Giả sử chỉ cần biết có đơn hàng phù hợp hay không:

```java
@Transactional(readOnly = true)
public boolean hasExportableOrder() {
    try (Stream<PurchaseOrder> orders =
            repository.findByStatus("PENDING")) {

        return orders.anyMatch(PurchaseOrder::isExportable);
    }
}
```

`anyMatch` có thể ngừng khi tìm thấy phần tử đầu tiên thỏa điều kiện. Lệnh `return` vẫn làm chương trình rời khối tài nguyên, nên `close()` được gọi trước khi phương thức thực sự trả kết quả.

Tương tự, `findFirst`, `limit`, `break` trong vòng lặp duyệt iterator, hoặc exception từ handler đều không phải lý do bỏ qua bước đóng luồng.

Một điểm cần nhớ: `return` chỉ hoàn tất bình thường nếu quá trình đóng tài nguyên cũng hoàn tất bình thường. Nếu `close()` ném exception trong khi thân khối không có lỗi, exception đóng tài nguyên có thể khiến lời gọi thất bại thay vì trả giá trị như dự kiến.

Những ví dụ dùng `isExportable()` giả định đây là phương thức nghiệp vụ của `PurchaseOrder`. Nếu điều kiện có thể diễn đạt tốt trong truy vấn và chỉ cần kiểm tra tồn tại, hãy cân nhắc query `exists…By` được mô-đun hỗ trợ để tránh tải dữ liệu không cần thiết.

## 7. Exception trong xử lý và exception khi đóng

Có ba trường hợp cần phân biệt:

| Thân khối `try` | `close()` | Kết quả |
| --- | --- | --- |
| Thành công | Thành công | Tiếp tục bình thường |
| Ném exception | Thành công | Exception từ thân khối được truyền ra |
| Thành công | Ném exception | Exception khi đóng được truyền ra |
| Ném exception | Cũng ném exception | Exception từ thân khối là lỗi chính; lỗi đóng được gắn dạng suppressed |

Ví dụ thuần Java sau minh họa quy tắc, không mở kết nối cơ sở dữ liệu:

```java
import java.util.stream.Stream;

try (Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    numbers.forEach(number -> {
        if (number == 2) {
            throw new IllegalArgumentException("processing failed");
        }
    });

} catch (RuntimeException failure) {
    System.out.println(failure.getMessage());

    for (Throwable suppressed : failure.getSuppressed()) {
        System.out.println("suppressed: " + suppressed.getMessage());
    }
}
```

Kết quả minh họa:

```text
processing failed
suppressed: close failed
```

Khối `catch` ở đây chỉ dùng để quan sát quy tắc exception. Trong mã ứng dụng, cần xử lý hoặc truyền lỗi theo hợp đồng của tác vụ. Không biến lỗi xử lý hoặc lỗi đóng tài nguyên thành một kết quả thành công ngầm.

Cũng không nên chỉ nhìn lỗi đóng rồi kết luận đó là nguyên nhân đầu tiên khiến tác vụ thất bại. Khi chẩn đoán, hãy xem cả exception chính, nguyên nhân bên trong và các exception bị suppressed.

### 7.1. Vì sao không chỉ dùng finally thủ công?

Có thể quản lý tài nguyên bằng `try/finally`, nhưng rất dễ quên trường hợp luồng chưa khởi tạo hoặc làm exception từ `close()` che mất exception xử lý ban đầu.

Với tài nguyên hỗ trợ `AutoCloseable`, `try-with-resources` thể hiện ý định trực tiếp và áp dụng quy tắc suppressed exception chuẩn của Java. Thông thường không cần thêm một lời gọi `close()` trong `finally` bên ngoài khối tài nguyên nữa.

## 8. Xác định rõ ai sở hữu luồng

Một quy ước dễ áp dụng là: nơi nhận luồng từ repository và quyết định toàn bộ quá trình tiêu thụ sẽ chịu trách nhiệm đóng nó. Nếu API chuyển quyền sở hữu sang bên gọi, phải thể hiện rõ hợp đồng đó.

| Tình huống | Trách nhiệm cần xác định |
| --- | --- |
| Service tự lấy và duyệt Stream | Service đóng trong cùng phạm vi xử lý |
| Helper chỉ nhận Stream để thực hiện một bước đồng bộ | Bên tạo vẫn quản lý, trừ khi hợp đồng nói helper nhận quyền sở hữu |
| API trả Stream cho caller | Caller phải đóng, và tài nguyên nền phải còn hợp lệ cho đến lúc tiêu thụ |
| Chuyển Stream thành Iterator | Vẫn phải giữ và đóng Stream sở hữu tài nguyên |
| Trả dữ liệu độc lập đã materialize | Đóng nguồn trước khi trả; cân nhắc dung lượng và lazy association |

### 8.1. Không trả luồng đã bị đóng

Mẫu sai:

```java
public Stream<PurchaseOrder> openPending() {
    try (Stream<PurchaseOrder> orders =
            repository.findByStatus("PENDING")) {
        return orders;
    }
}
```

Khi phương thức trả về, khối `try` đã đóng `orders`. Người gọi nhận một luồng có vòng đời đã kết thúc. Trả `orders.filter(...)` hoặc `orders.map(...)` từ cùng khối cũng không kéo dài vòng đời nguồn.

Nếu muốn service kiểm soát tài nguyên, hãy tiêu thụ kết quả trong service và trả về một kết quả độc lập như số lượng, tổng hợp hoặc DTO đã được chuẩn bị đầy đủ.

### 8.2. Không để transaction kết thúc trước khi duyệt

Mẫu dễ sai trong mô hình transaction qua proxy thông thường:

```java
@Transactional(readOnly = true)
public Stream<PurchaseOrder> openPending() {
    return repository.findByStatus("PENDING");
}
```

Với lời gọi thông thường không có transaction bao ngoài còn sống, phạm vi transaction của phương thức có thể kết thúc khi phương thức trả về. Caller bắt đầu duyệt sau đó có thể gặp tài nguyên không còn hợp lệ.

Ngay cả khi caller dùng `try-with-resources`, việc đóng đúng ở caller cũng không khôi phục một transaction đã kết thúc. Cần đặt cả bước lấy luồng, duyệt và đóng trong một phạm vi truy cập dữ liệu phù hợp, như service đồng bộ ở ví dụ trước.

### 8.3. Iterator không thay thế hợp đồng đóng nguồn

```java
import java.util.Iterator;
import java.util.stream.Stream;

try (Stream<PurchaseOrder> orders = repository.findByStatus("PENDING")) {
    Iterator<PurchaseOrder> iterator = orders.iterator();

    while (iterator.hasNext()) {
        PurchaseOrder order = iterator.next();
        handle(order);

        if (shouldStop(order)) {
            break;
        }
    }
}
```

`handle` và `shouldStop` là các hàm nghiệp vụ minh họa. Sau `break`, luồng vẫn được đóng khi rời khối. Nếu chỉ giữ `Iterator` và đánh mất tham chiếu tới Stream, caller có thể không còn cách rõ ràng để đóng tài nguyên nguồn.

## 9. Khi có nhiều tài nguyên

Tài nguyên trong `try-with-resources` được khởi tạo từ trái sang phải và đóng theo thứ tự ngược lại.

Ví dụ xuất mỗi định danh thành một dòng văn bản:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.stream.Stream;

@Transactional(readOnly = true)
public void writePendingIds(Path output) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
                output, StandardCharsets.UTF_8);
         Stream<PurchaseOrder> orders =
                repository.findByStatus("PENDING")) {

        Iterator<PurchaseOrder> iterator = orders.iterator();

        while (iterator.hasNext()) {
            writer.write(iterator.next().getId().toString());
            writer.newLine();
        }
    }
}
```

Trong ví dụ, `writer` được mở trước, `orders` được mở sau. Khi kết thúc, `orders` được đóng trước rồi mới đến `writer`. Nếu bước mở luồng thất bại sau khi writer đã mở thành công, writer vẫn được đóng.

Đây là minh họa thứ tự vòng đời tài nguyên. Việc ghi file thành công, transaction thành công và một job xuất dữ liệu hoàn tất là những trạng thái riêng. Nếu xử lý thất bại giữa chừng, file có thể chứa dữ liệu chưa đầy đủ; đóng tài nguyên không tự xóa file hoặc khôi phục các hiệu ứng đã xảy ra.

Tương tự, `try-with-resources` không thay đổi chính sách rollback của Spring đối với checked exception như `IOException`. Nếu nghiệp vụ có thao tác ghi dữ liệu cần rollback, chính sách transaction phải được thiết kế riêng.

## 10. Không nhầm Stream với Streamable và wrapper

Trong chương về luồng và wrapper, tên kiểu có thể gần nhau nhưng hợp đồng khác nhau:

| Kiểu hoặc nguồn | Điểm cần nhớ |
| --- | --- |
| `Stream<T>` từ repository hỗ trợ streaming | Tiêu thụ một lần; quản lý việc đóng và phạm vi tài nguyên |
| `collection.stream()` | Nguồn trong bộ nhớ thông thường không giữ cursor cơ sở dữ liệu |
| `Streamable<T>` của Spring Data Commons | Abstraction để duyệt và kết hợp dữ liệu; không phải một Stream đang mở |
| Wrapper tùy chỉnh quanh `Streamable` | Phải hiểu hợp đồng của wrapper; tên wrapper không quyết định vòng đời tài nguyên |

`Streamable` không phải `AutoCloseable` chỉ vì có phương thức `stream()`. Không đặt một đối tượng `Streamable` thông thường vào danh sách tài nguyên và mong Java tự biết đóng cursor phía dưới.

Ngược lại, bọc một `Stream` đang mở thành `Iterable` hoặc một wrapper khác không tự chuyển giao hay kết thúc nghĩa vụ đóng nguồn. Nếu thiết kế wrapper nắm tài nguyên, wrapper cần một hợp đồng sở hữu và đóng rõ ràng, thay vì che mất tham chiếu tới tài nguyên thật.

Bài học này tập trung vào query method trả trực tiếp `Stream<T>`. Các kiểu reactive có hợp đồng subscription, cancellation và quản lý tài nguyên riêng; không áp dụng cú pháp đóng Stream của Java một cách máy móc cho chúng.

## 11. Các giới hạn mà try-with-resources không giải quyết

### 11.1. Không bảo đảm dữ liệu được lấy từng hàng từ server

`Stream<T>` mô tả cách ứng dụng xử lý dữ liệu bằng pipeline. Driver hoặc mô-đun có thể cần cấu hình fetch size, cursor hoặc transaction để lấy dữ liệu từng đợt; một số triển khai có thể vẫn materialize dữ liệu trước.

Vì vậy cần phân biệt ba câu hỏi: API có trả Stream không, hạ tầng có đọc theo đợt không, và ứng dụng có giữ lại toàn bộ kết quả không. Đóng đúng luồng chỉ trực tiếp giải quyết vòng đời tài nguyên.

### 11.2. Không giới hạn bộ nhớ của mọi pipeline

Các thao tác như `collect(toList())`, `sorted()` hoặc việc đưa mọi phần tử vào một collection bên ngoài có thể giữ nhiều dữ liệu. Với entity được quản lý, persistence context của một số mô-đun cũng có thể làm bộ nhớ tăng theo quá trình duyệt.

Khi xử lý tập rất lớn, cần đánh giá cả pipeline, kiểu kết quả, ngữ cảnh quản lý entity và chiến lược lấy dữ liệu. Nếu phù hợp và được kho dữ liệu hỗ trợ, phân trang hoặc scrolling theo từng cửa sổ có thể cho phạm vi xử lý dễ kiểm soát hơn.

### 11.3. Không làm Stream truy cập dữ liệu an toàn khi chạy song song

Không tự thêm `.parallel()` để tăng tốc một luồng đang đọc qua cursor hoặc session. Những tài nguyên đó thường có ràng buộc thread, và ngữ cảnh transaction kiểu thread-bound không tự được truyền sang các worker thread của parallel stream.

Nếu cần xử lý song song, hãy tách chiến lược đọc, chia công việc và transaction của từng đơn vị xử lý theo khả năng kho dữ liệu. Đóng luồng đúng vẫn cần thiết nhưng không làm mất các ràng buộc này.

### 11.4. Không cho phép công việc bất đồng bộ dùng nguồn sau khi đóng

Một callback đồng bộ có thể gửi task vào executor rồi trả về ngay. Khi vòng `forEach` và khối `try` kết thúc, Stream bị đóng nhưng task nền có thể còn chạy.

Không để task nền tiếp tục đọc iterator, luồng nguồn hoặc lazy association phụ thuộc vào session đã kết thúc. Nếu cần xử lý sau đó, hãy chuyển giao dữ liệu độc lập với phạm vi tài nguyên và thiết kế transaction ở nơi xử lý phù hợp.

### 11.5. Không tạo bảo đảm xử lý đúng một lần

Nếu đã gửi một phần dữ liệu đến hệ thống ngoài rồi mới gặp lỗi, việc đóng Stream không hoàn tác những lần gửi đã thành công. Lần chạy lại vẫn cần chính sách idempotency, checkpoint hoặc chống trùng theo yêu cầu tác vụ.

Luồng được đóng sạch sẽ là điều kiện vận hành tốt; nó không đồng nghĩa toàn bộ nghiệp vụ đã hoàn thành.

## 12. Dấu hiệu và cách kiểm tra lỗi vòng đời

| Hiện tượng | Khả năng cần xem xét | Cách kiểm tra |
| --- | --- | --- |
| Số connection bận tăng sau nhiều lần gọi | Luồng truy vấn chưa đóng, transaction kéo dài hoặc rò rỉ ở nơi khác | Kiểm tra phạm vi `try`, transaction và metric pool |
| Có kết quả lúc ít dữ liệu nhưng lỗi khi duyệt lâu | Tài nguyên nền hết hiệu lực, timeout hoặc phạm vi transaction sai | Đối chiếu thời điểm mở, duyệt, đóng và kết thúc transaction |
| Lỗi khi duyệt Stream do service trả về | Stream đã đóng hoặc transaction đã kết thúc trước khi tiêu thụ | Xem ranh giới phương thức và nơi caller duyệt |
| Đọc một phần bằng `findFirst` rồi tài nguyên vẫn bị giữ | Kết thúc sớm nhưng thiếu `close()` | Đặt nguồn trong `try-with-resources` |
| Có lỗi chính và lỗi suppressed | Xử lý thất bại đồng thời đóng tài nguyên cũng thất bại | Đọc đủ exception chain và suppressed exceptions |
| Heap tăng dù đã đóng Stream | Pipeline tích lũy dữ liệu hoặc persistence context tăng | Quan sát đối tượng được giữ trong lúc xử lý |
| Thêm `.parallel()` rồi phát sinh lỗi khó lặp lại | Vi phạm hợp đồng thread hoặc transaction | Trở lại cách đọc tuần tự và kiểm tra thiết kế song song |

Không kết luận mọi vấn đề connection đều do thiếu `close()`. Cần quan sát tài nguyên thực tế, thời gian transaction và khả năng driver. Đặc biệt, một luồng đã đóng vẫn có thể nằm trong transaction chưa hoàn tất.

## 13. Các ca kiểm chứng nên có khi tích hợp thực tế

Những tình huống sau giúp kiểm tra thiết kế vòng đời:

1. **Kết quả rỗng:** khối xử lý không gọi handler nhưng vẫn đóng luồng.
2. **Duyệt toàn bộ:** đóng nguồn sau phần tử cuối và hoàn tất phương thức bình thường.
3. **Kết thúc sớm:** dùng `findFirst`, `anyMatch` hoặc `break` mà vẫn đóng nguồn.
4. **Handler ném exception:** không bỏ qua bước đóng; lỗi chính vẫn được truyền theo hợp đồng.
5. **Đóng nguồn thất bại:** tác vụ không bị báo thành công ngầm; quan sát được lỗi đóng.
6. **Cả xử lý lẫn đóng cùng thất bại:** lỗi đóng xuất hiện trong suppressed exceptions.
7. **Lời gọi qua Spring proxy:** transaction còn hiệu lực trong lúc tiêu thụ nếu mô-đun yêu cầu.
8. **Nhiều lần gọi liên tiếp:** tài nguyên không tăng vô hạn sau các lượt thành công và thất bại.
9. **Tập dữ liệu lớn:** kiểm tra cả bộ nhớ, thời gian giữ connection và cách driver lấy dữ liệu.

Một Stream thuần Java có `onClose` phù hợp để minh họa việc thoát scope có gọi close handler. Nó không chứng minh cursor hoặc connection thật được quản lý đúng bởi một mô-đun kho dữ liệu.

Muốn kiểm tra đặc tính truy cập dữ liệu thực tế, cần ca tích hợp với mô-đun, driver và cấu hình transaction đang dùng. Thời điểm connection về pool phải được đánh giá theo ranh giới transaction, không chỉ theo thời điểm đóng Stream.

## 14. Câu hỏi tự đánh giá

### A. Đã collect xong thì còn phải đóng không?

Một service gọi query trả Stream rồi `collect(toList())`, không giữ tham chiếu tới Stream và không có `try-with-resources`.

Hãy chỉ ra hai trách nhiệm bị nhầm lẫn và viết lại phạm vi xử lý. Sau khi sửa việc đóng nguồn, giải thích vì sao bộ nhớ vẫn có thể tăng theo số phần tử.

### B. Chỉ cần phần tử đầu

Một tác vụ dùng `findFirst()` trên luồng truy vấn. Người viết cho rằng vì chỉ đọc một phần tử nên không đáng lo về tài nguyên.

Giải thích vì sao dừng sớm vẫn cần đóng nguồn và cách đặt `return` an toàn trong khối tài nguyên.

### C. Service trả Stream ra ngoài

Phương thức có `@Transactional(readOnly = true)` trả trực tiếp Stream; controller bắt đầu duyệt sau khi service trả về.

Xác định ranh giới transaction cần kiểm tra. Đề xuất cách để service giữ quyền sở hữu luồng và trả kết quả độc lập hoặc xử lý qua callback đồng bộ.

### D. Đóng trong finally

Handler ném lỗi nghiệp vụ, sau đó lời gọi `close()` thủ công trong `finally` cũng ném lỗi.

Phân tích nguy cơ che mất lỗi đầu tiên. Nêu quy tắc exception tương ứng khi dùng `try-with-resources`.

### E. Stream đóng rồi nhưng connection vẫn bận

Trong một transaction dài, ứng dụng đóng Stream sau một khối đọc nhỏ nhưng vẫn tiếp tục làm việc trước khi phương thức kết thúc.

Giải thích vì sao chưa thể kết luận `close()` thất bại. Phân biệt tài nguyên kết quả truy vấn với connection gắn transaction.

### F. Gửi công việc sang executor

Trong `forEach`, chương trình gửi các entity vào executor rồi kết thúc khối `try`. Task nền sau đó đọc một lazy association.

Xác định dữ liệu hoặc tài nguyên nào đã vượt khỏi phạm vi hợp lệ. Đề xuất cách chuyển giao dữ liệu độc lập và đặt transaction theo yêu cầu của từng đơn vị xử lý.

## 15. Quy tắc thực hành

Khi query method trả `Stream<T>`, hãy đặt việc lấy luồng, tiêu thụ và đóng trong một phạm vi có người sở hữu rõ ràng. Dùng `try-with-resources` ngay tại phạm vi đó, duy trì transaction phù hợp với mô-đun trong suốt lúc đọc và tránh để pipeline hoặc iterator thoát ra ngoài.

Luôn tách biệt bốn việc: terminal operation yêu cầu tính kết quả, `close()` kết thúc vòng đời luồng, transaction quản lý ngữ cảnh truy cập dữ liệu, còn nghiệp vụ quyết định thế nào là hoàn thành và thử lại an toàn.