# Chụp dữ liệu đầu vào phù hợp trước khi chuyển sang luồng khác

Trong ứng dụng **Spring Framework - concurrency**, một HTTP request có thể nhận dữ liệu, gọi service, rồi giao một phần công việc cho **Executor**, **@Async** hoặc **CompletableFuture**. Ngay lúc giao việc, luồng khác chưa chắc đã bắt đầu chạy; thậm chí nó có thể chỉ chạy sau khi HTTP request kết thúc. Nếu tác vụ bất đồng bộ tiếp tục tham chiếu đến dữ liệu **có thể thay đổi, bị giải phóng hoặc không còn thuộc phạm vi hợp lệ**, kết quả sẽ không ổn định và có nguy cơ lộ dữ liệu giữa các request.

Nguyên tắc cốt lõi của bài **“Chụp dữ liệu đầu vào phù hợp trước khi chuyển sang luồng khác”** là: **xác định chính xác tác vụ cần dữ liệu gì, lấy một bản snapshot thích hợp ở thời điểm giao việc, xác định ai sở hữu bản đó và không để bên gửi tiếp tục sửa những phần mà tác vụ cần coi là bất biến**.

Đây là bài thuộc nhóm **Gửi và nhận tác vụ**. Nó không yêu cầu sao chép mù quáng mọi đối tượng: “phù hợp” nghĩa là **đủ dữ liệu, có vòng đời đúng, bất biến ở mức cần thiết, không chứa bí mật dư thừa và có cách xử lý lỗi/giới hạn tài nguyên phù hợp**.

## 1. Ranh giới giữa luồng nhận request và luồng làm việc

Giả sử request A đặt một đơn hàng:

~~~text
HTTP request thread
  |
  | 1. Đọc payload, principal, requestId
  | 2. Kiểm tra, chuẩn hóa dữ liệu
  | 3. Tạo snapshot cho tác vụ
  | 4. executor.submit(() -> process(snapshot))
  |
  +-------------------------------> Worker thread
  |                                    |
  |                                    | 5. Có thể chạy trễ
  |                                    | 6. Dùng snapshot đã nhận
  |                                    v
  +--> HTTP request kết thúc       Xử lý kết quả
~~~

Hai luồng không có một “vùng biến cục bộ chung” mặc định. Khi truyền một đối tượng vào lambda hoặc phương thức bất đồng bộ, Java thường chuyển **giá trị tham chiếu đến đối tượng**, không tự chụp một bản sao toàn bộ object graph. Nếu bên gửi và bên nhận cùng trỏ đến một **ArrayList**, **HashMap** hoặc DTO có setter, chúng có thể quan sát những lần sửa của nhau.

Nói cách khác:

- **Giao việc**: executor nhận một Runnable/Callable hoặc Spring proxy chuyển phương thức @Async tới một TaskExecutor.
- **Chụp dữ liệu**: ứng dụng quyết định giá trị nào được sao chép, đối tượng nào được tạo mới và mức bất biến nào cần bảo đảm.
- **Chạy tác vụ**: worker sử dụng những giá trị đã nhận; worker không nên tự giả định rằng request, session, transaction hoặc ThreadLocal của caller còn tồn tại.
- **Nhận kết quả**: Future/CompletableFuture cho biết trạng thái của công việc, không tự giải quyết tính an toàn của những input mà task đã đọc.

## 2. “Capture biến” của lambda không phải “snapshot dữ liệu”

Xét đoạn code:

~~~java
List<String> items = new ArrayList<>();
items.add("book");

executor.execute(() -> process(items));

items.add("pen");
~~~

Đây là **đoạn mã minh họa** (giả sử có các import, executor và process). Lambda giữ một tham chiếu đến cùng **List**. Biến cục bộ items không bị gán lại nên thỏa điều kiện **effectively final**, nhưng **đối tượng ArrayList vẫn mutable**. Worker có thể đọc danh sách sau khi đã có phần tử pen, trước khi có pen, hoặc gặp vấn đề an toàn luồng nếu hai bên truy cập/ghi không đồng bộ.

Không nên nói rằng task “đã nhận [book]” chỉ vì lời gọi **execute** xảy ra trước dòng **items.add**. Điều kiện effectively final chỉ giới hạn **việc gán lại biến được lambda capture**, không đóng băng trạng thái của đối tượng mà biến trỏ tới.

Thêm **final** cũng chưa giải quyết:

~~~java
final List<String> items = new ArrayList<>();
items.add("book");
// items = new ArrayList<>(); // Không được gán lại.
items.add("pen");             // Vẫn được sửa đối tượng!
~~~

Có hai loại tách biệt:

| Tình huống | Có đổi được tham chiếu? | Có đổi được dữ liệu bên trong? |
| --- | --- | --- |
| Biến local effectively final trỏ tới ArrayList | Không gán lại trong phạm vi capture | **Có** |
| Field final trỏ tới HashMap | Không gán lại field | **Có** |
| record chứa List mutable | Không gán lại component | **Có**, nếu List vẫn mutable |
| record chứa List.copyOf của String | Không gán lại component | List không sửa trực tiếp được; String cũng bất biến |
| DTO chứa nested object mutable | Tùy khai báo | **Có thể**, cần snapshot sâu hơn |

Vì vậy, câu hỏi không phải “tham số có final không?” mà là **“mọi dữ liệu worker cần đọc còn có thể thay đổi qua một tham chiếu khác không?”**.

## 3. Ví dụ Java 17: worker đọc nhầm dữ liệu vì tham chiếu bị sửa

Ví dụ độc lập sau cố ý chụp **tham chiếu**, không chụp giá trị. Chúng ta dùng **CountDownLatch** để tạo một tình huống xác định: worker đã nhận input, nhưng phải đợi caller sửa nó xong mới được đọc.

Lưu thành **CapturedReferenceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CapturedReferenceDemo {
    static final class MutableRequest {
        String owner = "An";
        final List<String> tags =
                new ArrayList<>(List.of("standard"));
    }

    public static void main(String[] args) throws Exception {
        MutableRequest request = new MutableRequest();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch allowRead = new CountDownLatch(1);

        try {
            Future<String> result = executor.submit(() -> {
                workerReady.countDown();
                allowRead.await();
                return request.owner + " " + request.tags;
            });

            if (!workerReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker không bắt đầu trong thời hạn test");
            }

            request.owner = "Bình";
            request.tags.add("urgent");
            allowRead.countDown();

            System.out.println("Worker đọc: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            allowRead.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CapturedReferenceDemo.java
java CapturedReferenceDemo
~~~

**Stdout**, nếu worker khởi động trong thời hạn test:

~~~text
Worker đọc: Bình [standard, urgent]
~~~

**Giải thích từng bước:**

1. Worker có tham chiếu đến cùng **MutableRequest** mà caller đang giữ.
2. Worker báo đã bắt đầu, rồi đợi **allowRead**.
3. Caller thay owner và thêm tag mới, sau đó mở latch.
4. Worker đọc **giá trị hiện tại sau khi bị sửa**, không phải giá trị tại lúc submit.
5. **CountDownLatch** tạo quan hệ đồng bộ cần thiết, giúp ví dụ có kết quả xác định. Không dùng Thread.sleep để đoán thứ tự chạy.

Ví dụ này chủ động mô phỏng sai lầm thiết kế. Nếu caller sửa ArrayList trong lúc worker đang duyệt nó mà không có đồng bộ, còn có thể xuất hiện race hoặc ConcurrentModificationException; nhưng **không nên khẳng định ConcurrentModificationException chắc chắn xảy ra**. Kết quả phụ thuộc lịch chạy và kiểu thao tác.

## 4. Cách sửa mặc định: snapshot trước khi submit

Tạo một đối tượng **chỉ chứa dữ liệu cần cho công việc**, bằng immutable scalars và collection copy khi thích hợp. Chụp snapshot **trên thread đang sở hữu dữ liệu**, **trước** khi giao việc, trong khi dữ liệu còn ở trạng thái nhất quán.

Lưu thành **InputSnapshotDemo.java**, chạy độc lập với Java 17:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InputSnapshotDemo {
    static final class MutableRequest {
        String owner = "An";
        final List<String> tags =
                new ArrayList<>(List.of("standard"));
    }

    record JobSnapshot(String owner, List<String> tags) {
        JobSnapshot {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) throws Exception {
        MutableRequest request = new MutableRequest();

        // Snapshot tạo trước khi đưa công việc vào executor.
        JobSnapshot snapshot =
                new JobSnapshot(request.owner, request.tags);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch allowRead = new CountDownLatch(1);

        try {
            Future<String> result = executor.submit(() -> {
                workerReady.countDown();
                allowRead.await();
                return snapshot.owner() + " " + snapshot.tags();
            });

            if (!workerReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker không bắt đầu trong thời hạn test");
            }

            request.owner = "Bình";
            request.tags.add("urgent");
            allowRead.countDown();

            System.out.println("Dữ liệu nguồn: "
                    + request.owner + " " + request.tags);
            System.out.println("Snapshot của task: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            allowRead.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InputSnapshotDemo.java
java InputSnapshotDemo
~~~

**Stdout** (worker khởi động thành công):

~~~text
Dữ liệu nguồn: Bình [standard, urgent]
Snapshot của task: An [standard]
~~~

Tại sao bản sửa an toàn hơn?

- **owner** là String immutable, chụp giá trị tham chiếu String tại thời điểm snapshot là đủ.
- **List.copyOf(tags)** tạo một collection không thể chỉnh sửa qua các phương thức List, độc lập với những lần thêm/xóa phần tử khỏi ArrayList nguồn sau đó.
- Các phần tử trong ví dụ là **String** cũng immutable, nên không còn nhánh mutable bên trong List này.
- Worker chỉ nhận **snapshot**, không giữ **request** mutable hay đọc lại trạng thái gốc sau khi task đã được giao.
- Record bảo đảm tham chiếu các component không đổi sau khi khởi tạo; **copy phòng vệ của collection** bảo đảm phần dữ liệu list không bị sửa thông qua alias.

Lệnh **List.copyOf** không phải “phép màu đồng bộ”: nếu có một thread khác **đang sửa collection nguồn ngay trong lúc tạo snapshot**, thao tác copy có thể không có kết quả nhất quán hoặc có lỗi. Để snapshot đúng, trước tiên phải có **quyền sở hữu dữ liệu tạm thời**, dùng **lock**, **immutable input đã được publish an toàn** hoặc một cơ chế đồng bộ phù hợp.

## 5. Shallow copy và deep snapshot: phải nhìn cả object graph

Lỗi tiếp theo là tạo list mới nhưng mỗi phần tử vẫn là cùng một đối tượng mutable.

~~~java
List<MutableLine> copied = List.copyOf(originalLines);
~~~

Đây là **đoạn minh họa**. Dù **copied** không cho thêm/xóa phần tử, nếu một **MutableLine** đã có trong list đổi giá hoặc mã hàng, worker vẫn quan sát **đối tượng phần tử bị đổi**.

Một ví dụ độc lập, lưu thành **NestedSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedSnapshotDemo {
    static final class MutableLine {
        String sku;

        MutableLine(String sku) {
            this.sku = sku;
        }
    }

    record LineView(String sku) {
    }

    public static void main(String[] args) {
        MutableLine line = new MutableLine("SKU-01");
        List<MutableLine> source = new ArrayList<>();
        source.add(line);

        // Chỉ tạo list không sửa được; phần tử vẫn là MutableLine gốc.
        List<MutableLine> shallow = List.copyOf(source);

        // Chụp riêng dữ liệu cần thiết thành record chứa String.
        List<LineView> deepEnough = source.stream()
                .map(item -> new LineView(item.sku))
                .toList();

        line.sku = "SKU-02";

        System.out.println("Shallow thấy: " + shallow.get(0).sku);
        System.out.println("Snapshot thấy: "
                + deepEnough.get(0).sku());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NestedSnapshotDemo.java
java NestedSnapshotDemo
~~~

Stdout:

~~~text
Shallow thấy: SKU-02
Snapshot thấy: SKU-01
~~~

Trong ví dụ, **deepEnough** là một “deep snapshot đủ dùng” vì worker chỉ cần trường String sku. Nó không sao chép mọi thứ trong đối tượng nguồn mà chỉ lấy **giá trị có ý nghĩa với tác vụ**.

Các trường hợp cần suy nghĩ thêm:

| Dữ liệu gốc | Cách chụp thường phù hợp | Lưu ý |
| --- | --- | --- |
| String, enum, UUID | Giữ giá trị đã lấy | Các kiểu này là immutable |
| Primitive hoặc boxed immutable | Copy giá trị | Chọn đúng thời điểm đọc |
| List<String> | **List.copyOf(source)** | Phần tử String immutable; null bị từ chối |
| Set<String> | **Set.copyOf(source)** | Null bị từ chối; thứ tự duyệt không nhất thiết giữ theo nguồn |
| Map<String, String> | **Map.copyOf(source)** | Key/value không được null; key/value cần immutable |
| List<MutableDTO> | Chuyển từng phần tử thành immutable view/record mới | Copy list thôi chưa đủ |
| Mảng byte[] | **Arrays.copyOf(source, source.length)** | Mảng vẫn mutable; không chia sẻ reference nếu cần cô lập |
| Map<String, List<MutableDTO>> | Chụp map, list và từng DTO theo nhu cầu | Tránh alias ở nhiều cấp |
| Thực thể JPA/Hibernate | Chụp ID và field cần dùng, hoặc tải lại trong worker với transaction riêng | Không mang persistence context/entity mutable qua thread |
| Dữ liệu streaming/MultipartFile | Chụp nội dung/đường dẫn bền vững khi hợp lý, giới hạn kích thước | Vòng đời file/stream có thể kết thúc cùng request |

**Record không tự động deep immutable.** Một record như **record Payload(List<MutableDTO> items)** vẫn giữ tham chiếu tới list/element, trừ khi constructor chủ động phòng vệ và các phần tử được chuyển thành dạng phù hợp.

## 6. “Phù hợp” nghĩa là chụp dữ liệu tối thiểu và rõ nguồn gốc

Không cần copy toàn bộ HTTP request hay toàn bộ domain object. Tự hỏi:

1. Worker **thật sự cần thông tin gì** để hoàn thành công việc? Thường chỉ cần requestId, userId, mã tài nguyên, thời hạn, một vài tham số đã kiểm tra.
2. Dữ liệu có **bị caller mutate** sau submit không? Có nhánh collection/DTO mutable nào không?
3. Dữ liệu gốc có phụ thuộc vào **request scope, session, transaction, thread context, connection hay stream** sẽ hết hạn trước khi worker dùng không?
4. Dữ liệu có **nhạy cảm** không? Có đang sao chép cả mật khẩu, access token hoặc thông tin định danh mà worker không cần?
5. Nếu worker chạy **rất trễ** hoặc task bị retry, bản chụp có còn đúng về mặt nghiệp vụ không? Có cần tải lại trạng thái mới nhất từ database?
6. Bản chụp có **quá lớn** để giữ trong hàng đợi executor không? Có cần thay bằng ID/tham chiếu tới lưu trữ bền vững không?

Ví dụ một task gửi email thông báo hóa đơn có thể chỉ cần:

~~~java
public record EmailJobInput(
        String requestId,
        long invoiceId,
        String recipientId,
        String templateKey
) {
}
~~~

Đây là **định nghĩa record Java 17 độc lập** nhưng chỉ là **mảnh code mẫu**, không có main. Worker có thể nhận invoiceId và tải thông tin hóa đơn trong một transaction riêng, thay vì giữ cả đối tượng JPA EntityManager cùng với một cây object lớn từ request.

Trường hợp ngược lại, nếu yêu cầu là “gửi chính xác nội dung người dùng đã xác nhận tại thời điểm submit”, chỉ gửi ID rồi đọc lại dữ liệu **có thể đã đổi** cũng sai. Khi đó cần chụp immutable payload đã chuẩn hóa, snapshot có version, hoặc lưu một bản ghi giao dịch có tính bền vững để worker đọc đúng phiên bản. **Chọn dữ liệu nào được snapshot là quyết định nghiệp vụ**, không chỉ là chuyện Java syntax.

## 7. Java Memory Model: visibility không thay thế isolation

Trong Java, **ExecutorService** có quy tắc memory consistency quan trọng: những hành động trong thread trước khi gửi Runnable/Callable tới ExecutorService **happens-before** hành động của task đó; hành động của task xảy ra trước các bước sau khi một thread khác **Future.get()** trả về thành công.

Điều này giúp **công bố dữ liệu đã chuẩn bị trước submit** tới worker theo hợp đồng bộ thực thi. Tuy nhiên:

- Nó **không biến một ArrayList thành thread-safe**.
- Nó **không cấm** caller sửa input sau khi đã submit.
- Nó **không tự sao chép** object graph được lambda tham chiếu.
- Nó **không bảo đảm** một chuỗi nhiều field đọc từ nguồn mutable cùng thuộc về một phiên bản nhất quán nếu thread khác đang viết đồng thời.

Ví dụ:

~~~text
Caller: chuẩn bị list -> submit(task) -> sửa list
                           |
Worker:                 đọc list (bất cứ khi nào được chạy)
~~~

Quan hệ **trước submit → task** giúp publish trạng thái trước đó; đoạn **sửa list sau submit** có thể cạnh tranh với worker. Vì vậy, **snapshot + quyền sở hữu rõ** là giải pháp thiết kế, chứ không chỉ tăng volatile hoặc khóa một biến riêng lẻ.

Nếu tác vụ cần “một ảnh chụp tại cùng thời điểm” của nhiều trường trên một object mà **thread khác đồng thời cập nhật**, phải có một chiến lược nhất quán:

- Chặn mutate trong giai đoạn copy bằng **synchronized/Lock** dùng chung với writer.
- Xây object immutable hoàn chỉnh trước khi publish rồi **thay cả tham chiếu** bằng một publication mechanism đúng, thay vì sửa từng field.
- Đọc một **transaction snapshot** hoặc thông tin có version từ kho dữ liệu có bảo đảm phù hợp.
- **Chuyển quyền sở hữu** dữ liệu sang worker và cam kết caller không sửa nữa, nếu protocol thực sự cho phép.

Chỉ tạo **new ArrayList<>(source)** trong lúc một thread khác đang sửa source không phải một giao dịch snapshot nguyên tử.

## 8. Constructor copy phòng vệ: cả lúc nhận lẫn lúc trả dữ liệu

Một kiểu tổ chức tốt là tạo record hoặc final class có invariant rõ ràng:

~~~java
import java.util.List;
import java.util.Objects;

public record PriceJob(String orderId, List<Long> amounts) {
    public PriceJob {
        orderId = Objects.requireNonNull(orderId).strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId rỗng");
        }
        amounts = List.copyOf(amounts);
    }
}
~~~

Đây là **tệp PriceJob.java chạy được khi được dùng bởi mã gọi phù hợp**, không phải một chương trình có main. Nó yêu cầu **orderId** không null/rỗng và sao chép danh sách. Các phần tử **Long** immutable, nên phần dữ liệu worker cần đọc được cô lập tốt nếu caller đã sở hữu nguồn khi xây record.

Không phải mọi kiểu chỉ cần **List.copyOf**. Với **byte[]**, ngay cả một field final vẫn có thể bị sửa nếu trả ra mảng gốc. Một class có mảng cần copy phòng vệ cả ở constructor và getter:

~~~java
import java.util.Arrays;

public final class BinaryPayload {
    private final byte[] bytes;

    public BinaryPayload(byte[] input) {
        this.bytes = Arrays.copyOf(input, input.length);
    }

    public byte[] bytes() {
        return Arrays.copyOf(bytes, bytes.length);
    }
}
~~~

Đây là **lớp Java độc lập, không có main**. Nếu getter trả thẳng bytes, code bên ngoài vẫn có thể sửa dữ liệu của instance. Với payload lớn, chi phí copy cần được cân nhắc; có thể dùng file/blob bền vững theo ID và quản lý quyền truy cập thay vì copy khối bộ nhớ lớn cho từng task.

**List.copyOf** và **Collections.unmodifiableList** không hoàn toàn giống nhau. **Collections.unmodifiableList(source)** thường là *view* không cho sửa qua view nhưng vẫn phản ánh những lần thay đổi trên list gốc. **List.copyOf(source)** tạo dữ liệu collection không bị ảnh hưởng bởi việc thêm/xóa phần tử nguồn sau đó (với điều kiện copy từ nguồn nhất quán). Cả hai vẫn không tự biến phần tử mutable thành immutable.

## 9. Spring MVC và @Async: lấy snapshot ở request boundary

Đây là trường hợp rất thường gặp: controller nhận một HTTP request, biết user đã xác thực, rồi gọi một service chạy async. Điều đúng cần làm là **lấy những giá trị cần thiết trước**, tạo một đối tượng snapshot, chuyển nó cho service và để worker chỉ đọc bản đó.

Các tệp tiếp theo thuộc một **ứng dụng Spring MVC có Spring Web và Spring Context**, không phải ví dụ javac thuần. Mỗi khối là **một tệp Java riêng**, cần đặt đúng package.

**ReportJobInput.java** — snapshot của một tác vụ:

~~~java
package example.async;

public record ReportJobInput(
        String requestId,
        String userId,
        String title
) {
}
~~~

**ReportWorker.java** — service không lưu request input vào instance field:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("reportExecutor")
    public CompletableFuture<String> build(ReportJobInput input) {
        String message = "done:" + input.requestId()
                + ":" + input.userId()
                + ":" + input.title();

        return CompletableFuture.completedFuture(message);
    }
}
~~~

**ReportController.java** — chụp snapshot trước ranh giới @Async:

~~~java
package example.async;

import java.security.Principal;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ReportController {
    private final ReportWorker worker;

    public ReportController(ReportWorker worker) {
        this.worker = worker;
    }

    @PostMapping("/reports")
    public CompletableFuture<String> create(
            @RequestParam String title,
            Principal principal) {

        if (principal == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED);
        }

        String normalized = title.strip();
        if (normalized.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST);
        }

        ReportJobInput input = new ReportJobInput(
                UUID.randomUUID().toString(),
                principal.getName(),
                normalized
        );

        return worker.build(input);
    }
}
~~~

**AsyncConfig.java** — chọn executor có tên:

~~~java
package example.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

Đoạn trên là **ví dụ kỹ thuật minh họa truyền snapshot**, không phải hệ thống tạo báo cáo/bảo mật hoàn chỉnh. Spring quản lý vòng đời và khởi tạo bean ThreadPoolTaskExecutor khi cấu hình qua container.

Điều đáng chú ý:

1. Controller lấy **userId** từ **Principal**, không nhận userId do client tự truyền rồi tin tưởng.
2. Controller chuẩn hóa title và tạo **ReportJobInput** chứa **String immutable**, thay vì chuyển thẳng HttpServletRequest, Principal object hoặc request-scoped bean sang worker.
3. **@Async("reportExecutor")** xác định executor dùng cho service. Phương thức build được **controller bean khác** gọi qua Spring proxy; self-invocation thông thường trong cùng bean không kích hoạt interceptor @Async.
4. Controller trả **CompletableFuture** để MVC có thể kết nối xử lý bất đồng bộ với kết quả. Đây không phải một **durable background job**; kết quả và vòng đời request vẫn liên hệ tới HTTP response.
5. Khi nghiệp vụ cần phân quyền ở thời điểm thực thi, **userId đã snapshot không tự thay thế authorization**. Worker cần áp dụng các bước kiểm tra quyền thích hợp trước thao tác đặc quyền; ví dụ này chỉ tạo chuỗi kết quả.
6. Nếu executor quá tải, việc gửi tác vụ có thể **bị từ chối ngay tại lời gọi worker.build**. Snapshot đúng không đảm bảo task được tiếp nhận. Người gọi cần xử lý overload phù hợp.

Đừng đưa **@RequestScope bean** hoặc **HttpServletRequest** vào task rồi đọc sau khi request kết thúc. Một scoped proxy có thể không giải quyết được target khi worker không còn request context; session, servlet request và request attributes không có vòng đời theo executor task.

## 10. CompletableFuture: snapshot trước supplyAsync, không đợi đến trong lambda

Một anti-pattern khác:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> callExternalService(request.getOwner(),
                        request.getItems()),
                executor);
~~~

Đây là **đoạn minh họa**, giả sử request, executor và callExternalService tồn tại. Lambda sẽ lấy **owner** và **items** khi worker thực sự chạy; nó **không lấy chúng tại thời điểm tạo CompletableFuture**. Nếu caller sửa request hoặc vòng đời request đã hết, task có thể nhận dữ liệu khác ý định.

Cách đúng thường là:

~~~java
String owner = request.getOwner();
List<String> items =
        List.copyOf(request.getItems());

JobSnapshot snapshot = new JobSnapshot(owner, items);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> callExternalService(
                        snapshot.owner(),
                        snapshot.items()),
                executor);
~~~

Đây cũng là **đoạn minh họa** với các type và biến ngữ cảnh đã có. Quan trọng là **snapshot được tạo trước** lời gọi supplyAsync. **JobSnapshot** phải là immutable/defensive type phù hợp, không chỉ một DTO chứa collection mutable. Hàm **List.copyOf** vẫn yêu cầu nguồn đang ở trạng thái nhất quán lúc copy.

Với chuỗi CompletableFuture:

~~~java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(
                () -> load(snapshot), executor)
            .thenApply(data -> transform(data, snapshot))
            .thenCompose(data -> saveAsync(data, snapshot));
~~~

Đây là **pseudocode Java được chú thích dưới dạng đoạn minh họa**: phải tự khai báo Result, load, transform, saveAsync và snapshot tương ứng. Các stage nhìn thấy cùng snapshot đã chụp. Không giả định callback **thenApply** luôn chạy ở request thread; callback non-async có thể chạy trên thread hoàn tất stage trước hoặc thread đăng ký tùy trạng thái hoàn tất.

**Điểm cốt lõi:** việc dùng CompletableFuture tạo pipeline bất đồng bộ **không tự cô lập mutable input**. Snapshot và quyền sở hữu đối tượng vẫn là trách nhiệm của ứng dụng.

## 11. ThreadLocal, MDC và SecurityContext không phải bản snapshot tự động

Nhiều thông tin trong ứng dụng web được framework buộc vào thread: **MDC logging**, **SecurityContext** trong một số chiến lược, **RequestContextHolder**, transaction context. Khi gọi một Executor, task có thể chạy trên thread pool khác; thread đó **không mặc định giữ mọi ThreadLocal của caller**.

Các nguyên tắc:

- **Dữ liệu nghiệp vụ:** truyền trực tiếp qua tham số hoặc một immutable DTO.
- **Correlation/tracing:** dùng cơ chế propagation của framework quan sát/tracing hoặc một **TaskDecorator** được thiết kế đúng và dọn ngữ cảnh sau khi task kết thúc.
- **Bảo mật:** không tự copy toàn bộ SecurityContext/Principal một cách tùy tiện. Nếu framework và chính sách cho phép, dùng wrapper như **DelegatingSecurityContextAsyncTaskExecutor**; đảm bảo quyền được kiểm tra đúng thời điểm cần thiết.
- **Transaction:** transaction/persistence context ở thread gửi **không tự chuyển** sang worker. Thiết lập transaction boundary tại worker nếu cần truy cập dữ liệu giao dịch.
- **Request context:** không coi HttpServletRequest, request-scoped bean, request attributes hoặc MultipartFile là dữ liệu có thể tiếp tục dùng tùy ý sau khi response đã trả.
- **ThreadLocal tự viết:** nếu bắt buộc dùng, cần quản lý **set/restore/remove trong finally**. Thread pool tái sử dụng worker, nên bỏ quên cleanup có thể rò rỉ dữ liệu sang task sau.

Cũng cần phân biệt **context propagation** với **input snapshot**: propagation có thể phục hồi ngữ cảnh kỹ thuật phù hợp của một task, nhưng không bảo đảm DTO mutable được chụp đúng hoặc dữ liệu bảo mật còn hợp lệ khi worker thực thi.

## 12. Spring Data/JPA: ưu tiên ID và dữ liệu đã đóng băng, không đẩy EntityManager sang thread khác

Một lỗi phổ biến là đọc một entity trong transaction HTTP rồi đưa nguyên entity cho worker để xử lý về sau.

Rủi ro gồm:

- **EntityManager** và persistence context theo transaction không được thiết kế để chia sẻ tùy ý giữa các thread.
- Entity có thể có **lazy association**; worker truy cập sau khi transaction/session đã đóng có thể gặp lỗi tải dữ liệu.
- Entity mutable có thể đang bị caller hoặc tầng khác sửa, không bảo đảm một snapshot nhất quán.
- Dữ liệu trong DB có thể thay đổi giữa lúc submit và lúc worker xử lý.

Hai chiến lược cần phân biệt:

**A. Tác vụ phải dùng trạng thái mới nhất tại thời điểm thực thi.** Chỉ chụp **ID** và input nghiệp vụ tối thiểu, rồi worker mở transaction riêng và tải lại entity có kiểm tra version/authorization tương ứng.

~~~java
public record UpdateJob(long orderId, String actorId) {
}
~~~

**B. Tác vụ phải xử lý chính xác nội dung đã được người dùng duyệt tại thời điểm submit.** Chụp **immutable DTO chứa dữ liệu đã duyệt**, kèm **version** hoặc ghi một bản snapshot vào kho bền vững cùng transaction/outbox nếu cần. Chỉ gửi orderId rồi tải “phiên bản mới nhất” sẽ không tương đương với yêu cầu này.

Trong các quy trình có side effect và yêu cầu không mất việc, **executor nội bộ không phải hàng đợi bền vững**. Khi transaction gửi job thất bại hoặc ứng dụng restart, một Runnable trong RAM có thể mất. Cân nhắc **transactional outbox**, durable queue hoặc job store, cùng idempotency và cơ chế retry phù hợp.

## 13. Request body lớn, file và stream: không phải cứ copy toàn bộ vào RAM

Một snapshot phù hợp còn phải có **ngân sách tài nguyên**:

~~~text
10.000 job đang chờ
  x 2 MB payload copy mỗi job
  = khoảng 20.000 MB dữ liệu payload chưa kể overhead
~~~

Đây là **phép tính minh họa**, không phải metric thu được từ hệ thống. Copy toàn bộ byte[]/multipart input vào mỗi task có thể tăng mạnh bộ nhớ và gây GC pressure.

Với file:

1. Xác thực kích thước, định dạng và quyền truy cập **ở ranh giới request**.
2. Nếu worker chạy sau khi request kết thúc, **đừng dựa vào tài nguyên tạm của MultipartFile/request InputStream** còn tồn tại.
3. Khi phù hợp, đưa file vào storage có vòng đời rõ, ghi **objectKey, checksum, size, version** trong snapshot, và chỉ để worker tải phần cần dùng.
4. Bảo vệ storage key bằng quyền truy cập, không đặt nội dung nhạy cảm vào log hay URL công khai.
5. Xác định cleanup nếu task lỗi/cancel, nếu job không được nhận hoặc đã hoàn thành.

Với secret như token/password, snapshot chỉ những gì worker thực sự có quyền và cần sử dụng. Nếu có thể dùng **reference tới secret manager**, access scope ngắn, token riêng cho task hoặc cơ chế cấp lại theo quyền, đừng đưa cả request headers/cookie và access token vào hàng đợi dài hạn.

## 14. Cancellation, timeout và overload không bảo đảm dữ liệu được sử dụng

Ngay cả khi đã chụp snapshot chính xác, tác vụ có thể **không bao giờ thực thi**:

- Executor có thể reject task vì quá tải hoặc shutdown.
- Future có thể bị cancel; task có thể bị ngắt hoặc vẫn tiếp tục tùy implementation và tình trạng I/O.
- Worker có thể gặp lỗi trước khi dùng snapshot.
- Deadline ứng dụng có thể hết trước khi task bắt đầu.
- Executor queue có thể tích tụ backlog, khiến snapshot quá cũ so với nghiệp vụ.

Do đó, cần tách các câu hỏi:

| Câu hỏi | Cơ chế liên quan |
| --- | --- |
| Dữ liệu gửi đi có độc lập và đúng thời điểm? | Snapshot/immutability/ownership |
| Tác vụ đã được executor chấp nhận? | Submit result, TaskRejectedException, metrics |
| Tác vụ đã thực sự hoàn thành? | Future/CompletableFuture, trạng thái job |
| Tác vụ hoàn tất trong deadline? | Timeout/cancellation/queue wait |
| Tác vụ không mất khi ứng dụng restart? | Durable queue/job store/outbox |
| Tác vụ có quyền đọc/ghi tài nguyên? | Authorization tại thời điểm phù hợp |

**Snapshot đúng không tự giải quyết delivery semantics**. Người dùng gửi request và nhận HTTP 202 Accepted chỉ khi ứng dụng thật sự đã **tiếp nhận công việc theo hợp đồng**; một lệnh submit thất bại hoặc một Runnable bị drop im lặng không phải thành công nghiệp vụ.

## 15. Khi snapshot trở nên “cũ”: thời điểm và hợp đồng nghiệp vụ

“Chụp trước khi sang luồng khác” không có nghĩa dữ liệu đó **mãi đúng**. Ví dụ:

- **Đúng theo thời điểm submit:** một email xác nhận phải chứa danh sách sản phẩm và giá đã xác nhận lúc đặt hàng. Snapshot versioned/committed giúp tái hiện đúng nội dung lịch sử.
- **Đúng theo thời điểm xử lý:** một thao tác khóa tài khoản hoặc thanh toán có thể cần kiểm tra lại trạng thái hiện tại và quyền, ngay khi task chạy.
- **Cần kết hợp hai loại dữ liệu:** worker nhận immutable command cho ý định của người dùng, nhưng vẫn tải lại trạng thái hiện tại để kiểm tra điều kiện thực hiện.
- **Có retry:** mỗi lần retry nên biết giữ snapshot gốc hay làm mới dữ liệu; thay đổi ngầm sau retry có thể gây kết quả khác với yêu cầu ban đầu.

Trong thiết kế tốt, **snapshot thể hiện một contract**: ai tạo, thời điểm tạo, những field nào là giá trị cố định, field nào cần refresh, và ai chịu trách nhiệm xác thực/ghi nhận.

Nếu ứng dụng có nhiều bước bất đồng bộ, không nhất thiết dùng lại duy nhất một object chứa mọi dữ liệu từ đầu đến cuối. Có thể dùng **những DTO bất biến theo từng stage**, vừa đủ dùng, giảm rủi ro lộ dữ liệu sang thành phần không cần.

## 16. Test tốt: cố tình thay đổi dữ liệu gốc sau khi submit

Để biết hệ thống thật sự tách input khỏi task, test theo trình tự **có điều phối**:

1. Tạo input mutable có giá trị **A**.
2. Chụp snapshot đúng cách trước khi submit.
3. Gửi worker nhưng giữ worker chờ bằng **CountDownLatch**.
4. Sửa dữ liệu gốc sang **B**, bao gồm nested collection/element có nguy cơ shared.
5. Mở latch, để worker đọc snapshot.
6. Assert worker thấy **A**, trong khi caller nhìn nguồn **B**.
7. Dùng **Future.get(timeout)** để tránh test treo; release latch và shutdown executor trong finally.

Những ví dụ ở mục 3, 4 và 5 đã kiểm tra lần lượt lỗi **captured reference**, cách sửa bằng **List.copyOf với phần tử immutable**, và lỗi **shallow copy với phần tử mutable**.

**Test đồng thời không thể chỉ dựa vào Thread.sleep.** Nếu may mắn worker chạy trước khi caller mutate, test sẽ pass dù thiết kế sai. Latch/Barrier giúp đặt chính xác điểm xen kẽ. Đồng thời, phải test cả tình huống **copy trong lúc dữ liệu đang bị writer khác mutate**; nếu không có ownership hoặc lock, một copy API chưa bảo đảm consistency.

Với ứng dụng Spring, test thêm:

- Gọi **@Async** thông qua **Spring-managed proxy**, không chỉ gọi trực tiếp new Service().
- Đảm bảo worker không đụng **request scope/transaction cũ** khi request đã kết thúc.
- Với payload lớn, đo memory footprint của queue và bản snapshot.
- Khi submit bị **TaskRejectedException**, xác nhận chưa báo công việc đã được nhận.
- Khi task lỗi/cancel, cleanup tài nguyên tham chiếu trong snapshot có được thực hiện không.

## 17. Những lỗi tư duy thường gặp

**“Lambda capture biến effectively final nên dữ liệu bất biến.”** Sai. Effectively final chỉ nói về việc gán lại biến local; object mà nó trỏ đến vẫn có thể bị thay đổi.

**“Record làm tất cả các field sâu bên trong trở thành immutable.”** Sai. Record chỉ giữ các component references cố định; collection và object nested vẫn mutable nếu không copy/phòng vệ.

**“List.copyOf trên List<MutableDTO> bảo đảm mọi dữ liệu đã frozen.”** Sai. Nó không clone các phần tử.

**“Collections.unmodifiableList(source) là snapshot.”** Không nhất thiết. View unmodifiable có thể tiếp tục phản ánh thay đổi trên source list.

**“Cứ gọi submit trước thì worker chắc chắn đọc dữ liệu trước khi caller thay đổi.”** Sai. Executor có thể hoãn chạy task; ngay cả khi chạy đồng thời, thiếu ownership/đồng bộ vẫn nguy hiểm.

**“ExecutorService có happens-before nên không cần immutable snapshot.”** Sai. Happens-before hỗ trợ visibility cho các hành động đúng thứ tự, không tạo isolation cho các lần ghi diễn ra sau submit.

**“@Async tự mang HttpServletRequest, transaction và mọi ThreadLocal sang worker.”** Không được bảo đảm. Những context đó có phạm vi và cơ chế propagation riêng.

**“Chuyển JPA entity qua executor không sao nếu chỉ đọc.”** Không thể kết luận như vậy; proxy lazy loading, persistence context và các trạng thái mutable/transaction boundary có thể làm hành vi sai.

**“Chụp toàn bộ request để chắc chắn không thiếu dữ liệu.”** Không tốt: request chứa quá nhiều thông tin, có thể bao gồm token, stream, object sống ngắn và payload lớn.

**“Sao chép byte[] một lần là immutable mãi mãi.”** Nếu trả lại byte[] nội bộ hoặc worker tiếp tục mutate nó, dữ liệu vẫn thay đổi. Cần defensive copy khi nhập/xuất hoặc hợp đồng ownership nghiêm ngặt.

**“Một snapshot luôn đúng cho mọi retry.”** Không hẳn. Task có thể cần phiên bản tại thời điểm submit hoặc trạng thái mới nhất; phải xác định yêu cầu nghiệp vụ.

**“Gửi được Runnable tức là job đã durable.”** Sai. Executor trong RAM không thay thế hàng đợi công việc có lưu trữ bền vững.

## 18. Bài tập áp dụng

**Bài 1.** Controller tạo `List<String> filters`, rồi gọi `executor.execute(() -> search(filters))`. Sau đó controller thêm phần tử vào filters. Có thể xem filters đã được chụp chưa?

**Đáp án:** Chưa. Lambda giữ cùng tham chiếu List. Nếu worker cần nội dung tại thời điểm submit, tạo **List.copyOf(filters)** trước execute (và chắc chắn không có thread khác đang sửa filters khi copy).

**Bài 2.** Code dùng `final MutableOrder order` rồi truyền order tới @Async. Từ khóa final đã đủ chưa?

**Đáp án:** Chưa. Nó chỉ ngăn gán lại tham chiếu order trong phạm vi khai báo; các setter/nested collections của MutableOrder vẫn có thể bị thay đổi.

**Bài 3.** Dùng `List.copyOf(lines)` với mỗi Line có trường price mutable. Worker có thấy price mới sau khi caller đổi không?

**Đáp án:** Có thể. List mới giữ cùng các Line instances. Cần chuyển từng Line thành immutable snapshot của những giá trị worker cần.

**Bài 4.** Một worker gửi email sau một giờ cần dùng tên người nhận và địa chỉ ở đúng thời điểm đơn hàng được đặt. Chỉ gửi customerId rồi query hiện tại có đúng không?

**Đáp án:** Không chắc. Nếu khách đổi thông tin trong giờ đó, kết quả sẽ khác. Cần mô hình snapshot versioned/committed của dữ liệu đã xác nhận hoặc bản ghi lịch sử để giữ đúng ngữ nghĩa.

**Bài 5.** Worker chỉ cần orderId để tải trạng thái đơn hàng mới nhất và quyết định hành động. Có nhất thiết copy toàn bộ order DTO không?

**Đáp án:** Không. Chỉ gửi ID và command metadata tối thiểu, rồi tải lại dữ liệu trong transaction của worker, kiểm tra version/authorization thích hợp.

**Bài 6.** Vì sao một bản copy bằng `new ArrayList<>(sharedList)` chưa chắc có tính nhất quán?

**Đáp án:** Nếu thread khác đồng thời mutate sharedList mà không đồng bộ, quá trình copy có thể quan sát trạng thái không nhất quán. Cần ownership, lock hoặc immutable publication.

**Bài 7.** Snapshot chứa List.copyOf(strings) nhưng một phần tử String bị gán lại trong biến nguồn. Worker có thấy String mới không?

**Đáp án:** Không thông qua List snapshot đã tạo: String immutable và List copy giữ các phần tử đã có tại thời điểm tạo. Gán lại biến nguồn không thay giá trị String được giữ trong snapshot.

**Bài 8.** Tại sao không truyền trực tiếp HttpServletRequest hoặc EntityManager vào CompletableFuture chạy sau HTTP response?

**Đáp án:** Chúng có scope/vòng đời riêng, không được thiết kế để tùy ý truy cập trên worker sau khi request/transaction kết thúc. Chụp DTO/ID cần thiết và thiết lập lại ranh giới tài nguyên tại worker.

**Bài 9.** Đã chụp input đúng nhưng executor từ chối task. Có thể trả “đã xử lý” không?

**Đáp án:** Không. Chụp input đúng chỉ bảo đảm tính phù hợp của dữ liệu **nếu task được thực thi**. Phải xử lý trạng thái tiếp nhận, lỗi, retry và delivery semantics riêng.

## 19. Checklist trước khi giao tác vụ sang thread khác

- [ ] Xác định chính xác **task cần những trường nào**.
- [ ] Đọc dữ liệu **khi nguồn còn có chủ sở hữu và phạm vi hợp lệ**.
- [ ] Kiểm tra/chuẩn hóa input, tạo snapshot **trước submit**.
- [ ] Đảm bảo **immutable** ở mọi lớp cần thiết; phòng vệ với nested mutable objects.
- [ ] Không copy một collection đang bị sửa đồng thời nếu thiếu synchronization.
- [ ] Không đưa request/session/EntityManager/stream sống ngắn vào task tùy ý.
- [ ] Không sao chép secret, token và dữ liệu cá nhân dư thừa.
- [ ] Giới hạn dung lượng snapshot và số task tồn đọng.
- [ ] Xác định dữ liệu **cố định lúc submit** hay **cần tải lại lúc thực thi**.
- [ ] Có hợp đồng xử lý **rejection, timeout, cancel, retry và shutdown**.
- [ ] Kiểm thử bằng latch để xác minh sửa nguồn sau submit **không đổi dữ liệu task**.
- [ ] Gắn observability/tracing bằng cơ chế propagation an toàn khi cần, không coi nó là thay thế của snapshot.

## Kết luận

**“Chụp dữ liệu đầu vào phù hợp trước khi chuyển sang luồng khác”** nghĩa là xác định **thời điểm**, **quyền sở hữu**, **mức bất biến** và **vòng đời** của những giá trị worker cần. Với Java ExecutorService, CompletableFuture và Spring @Async, lambda hoặc proxy **không tự sao chép toàn bộ mutable input**. Cách tiếp cận mặc định tốt là **chuẩn hóa và xác thực dữ liệu trên request thread, tạo immutable DTO/record đủ dùng với defensive copies, rồi truyền snapshot qua tham số cho worker**. Khi dữ liệu lớn, thay đổi theo nghiệp vụ hoặc phải durable, dùng ID/version, kho lưu trữ phù hợp và transaction boundary riêng.

Một snapshot đúng không chỉ ngăn race condition: nó giúp tránh rò rỉ request context, giảm lỗi sau khi request/transaction kết thúc, hỗ trợ kiểm thử có tính xác định và làm rõ hợp đồng giữa luồng gửi với luồng xử lý.

**Tài liệu tham khảo kỹ thuật:** Java SE 17 API của **ExecutorService**, **Future**, **List.copyOf**, **Arrays.copyOf**, **CountDownLatch**; Spring Framework reference về **Task Execution and Scheduling**, **@Async**, request scopes và Spring MVC asynchronous requests; hướng dẫn Java Memory Model.
