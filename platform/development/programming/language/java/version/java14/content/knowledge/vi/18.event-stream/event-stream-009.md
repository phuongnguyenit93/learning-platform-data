# Chỉ mở tệp JFR và repository từ nguồn tin cậy khi dùng EventStream

## 1. Mục tiêu của bài học

`jdk.jfr.consumer.EventStream` cho phép ứng dụng Java nhận các sự kiện **Java Flight Recorder (JFR)**, bao gồm đọc một file recording đã tạo và theo dõi repository chứa dữ liệu JFR. Tuy nhiên, không phải file có đuôi `.jfr` hay thư mục có cấu trúc giống repository nào cũng là dữ liệu nên đưa thẳng vào bộ đọc.

Tài liệu API Java hiện hành nêu rõ hai yêu cầu quan trọng:

- Với **`EventStream.openFile(Path file)`**: chỉ nên mở **recording files từ nguồn tin cậy**.
- Với **`EventStream.openRepository(Path directory)`**: chỉ nên mở **disk repositories đáng tin cậy**.

Đây là **hợp đồng sử dụng an toàn của API**. Khi code nhận đường dẫn từ upload, tham số HTTP, CLI, message queue hoặc một tài khoản khác, bản thân đường dẫn đó **không chứng minh nguồn dữ liệu đáng tin**. Một file có đúng đuôi `.jfr` hoặc có thể parse thành công cũng **không được tự động tin cậy**.

**Phiên bản:** API `EventStream` có từ Java 14 và những lời cảnh báo chỉ mở file/repository tin cậy vẫn hiện diện trong tài liệu Java 17, 21, 26. Bài dùng ví dụ **Java 17+**, không dựa vào Security Manager như cơ chế bảo vệ chủ đạo và không sử dụng kỹ thuật cũ đã lỗi thời.

**Ý chính:** kiểm soát **nguồn cung cấp dữ liệu và quyền ghi vào file/repository trước khi mở**, đồng thời giới hạn chi phí xử lý và bảo vệ thông tin nhạy cảm. Không coi việc kiểm tra extension hoặc bắt `IOException` là giải pháp thay thế.

## 2. Ba cách tạo EventStream và phạm vi tin cậy

Các factory methods cần phân biệt:

| API | Nguồn dữ liệu | Điểm cần nhớ |
| --- | --- | --- |
| `EventStream.openFile(Path file)` | Một **file JFR recording** có sẵn | Mặc định stream bắt đầu ở sự kiện đầu tiên trong file; chỉ mở file từ nguồn tin cậy |
| `EventStream.openRepository(Path directory)` | Một **disk repository JFR** được chỉ rõ bằng `Path` | Chỉ mở repository tin cậy; mặc định bắt đầu từ sự kiện tiếp theo được Flight Recorder flush |
| `EventStream.openRepository()` | Repository của **JVM hiện tại** | Không nhận đường dẫn ngoài; mặc định bắt đầu từ sự kiện được flush tiếp theo |

Các phương thức này có thể ném `IOException` nếu không mở hoặc đọc được nguồn. Sau khi tạo stream, gọi `onEvent(...)` để đăng ký callback và `start()` hoặc `startAsync()` để tiêu thụ sự kiện. Dùng **try-with-resources** để đóng stream.

Ví dụ cấu trúc dùng file đáng tin cậy:

~~~java
// Ví dụ bên trong method; "trustedFile" do ứng dụng quản lý.
try (var stream = EventStream.openFile(trustedFile)) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.start(); // đọc cho đến khi xử lý xong nguồn file
}
~~~

Đây là **đoạn minh họa**, không phải file có `main` độc lập. Nó giả định biến `trustedFile` đã được nguồn cấu hình đáng tin cậy cung cấp; code không chấp nhận `Path` từ người gọi tùy ý. File có thể không chứa event `jdk.CPULoad`, nên callback không nhất thiết được chạy.

### File recording khác repository như thế nào?

Một **file recording** thường là file được xuất hoặc dump từ JFR để đọc lại, ví dụ `diagnostic.jfr`. Với `openFile`, bộ đọc bắt đầu từ đầu file theo mặc định và kết thúc khi hết dữ liệu.

Một **repository** là vùng lưu các **chunk JFR** dùng cho quá trình ghi/tiêu thụ dữ liệu JFR. Nó không đồng nghĩa một thư mục bất kỳ chứa vài file có đuôi `.jfr`. Khi dùng `openRepository(Path)`, ứng dụng có thể tương tác với vùng lưu dữ liệu đang được ghi và cập nhật. Do vậy quyền **thay đổi nội dung trong repository** đặc biệt quan trọng trong toàn bộ thời gian stream chạy.

`openRepository()` không có tham số là lựa chọn tự nhiên nếu muốn theo dõi repository của **JVM hiện tại**. Tuy nhiên, nó không tự động biến event fields thành dữ liệu đã được kiểm định cho mọi mục đích: ứng dụng vẫn phải xử lý giá trị và sự kiện phù hợp với hợp đồng của mình.

## 3. “Nguồn tin cậy” cần được hiểu cụ thể

**Tin cậy không phải một thuộc tính của tên file**. Khi quyết định đọc JFR, phải biết:

1. **Ai tạo recording?** JVM do hệ thống của mình quản lý, đội vận hành được ủy quyền, hay một người lạ tải file lên?
2. **Ai có thể thay đổi file hoặc repository?** Chỉ tài khoản dịch vụ/nhóm vận hành, hay một thư mục cho nhiều người dùng ghi?
3. **Đường dẫn được lấy từ đâu?** File ID được đối chiếu trong allowlist phía server hay đường dẫn tùy ý do request cung cấp?
4. **Có chuỗi bàn giao tin cậy không?** File được truyền qua kênh xác thực và lưu lại trong vùng được quản lý, hay chỉ có đường link/đính kèm không rõ nguồn?
5. **Nguồn có thể thay đổi sau kiểm tra không?** Nếu một tiến trình không tin cậy có quyền ghi hoặc thay thế đường dẫn, kiểm tra trước khi mở không đủ.
6. **Quyền truy cập nội dung có phù hợp không?** Recording có thể chứa thông tin về class, method, thread, đường dẫn, cấu hình hoặc các trường do ứng dụng ghi vào sự kiện JFR.

Một nguồn thường có thể được coi **phù hợp để dùng trong demo** khi chương trình **tự tạo** recording trong cùng tiến trình và đọc lại file vừa tạo. Ở production, mức độ tin cậy phải dựa trên **quyền sở hữu, kiểm soát file system, quyền truy cập, quá trình tạo và vận chuyển** chứ không phải tên thư mục.

Những ví dụ **không đủ làm bằng chứng tin cậy**:

- Có đuôi `.jfr` hoặc có header giống JFR.
- Có thể gọi `Files.isRegularFile(path)` và `Files.isReadable(path)`.
- Có đường dẫn bắt đầu bằng một prefix chuỗi như `"/opt/jfr"`.
- File nhỏ hơn một giới hạn dung lượng.
- Chạy `EventStream.openFile(path)` mà chưa thấy exception.
- File được đổi tên hoặc copy vào một thư mục mang tên `trusted` nhưng bên ngoài vẫn có thể sửa nó.
- Có mã SHA-256 được tải **cùng với file từ chính nguồn không đáng tin**. Hash như vậy chỉ xác nhận nội dung khớp với một giá trị do cùng người gửi khai báo, không xác thực nguồn.

Những kiểm tra trên có thể là **phụ trợ**, nhưng không tạo ra trust boundary. Đặc biệt, file JFR là **dữ liệu nhị phân** được parser giải mã; việc tiếp nhận dữ liệu nhị phân không đáng tin cần được đánh giá như mọi đầu vào chưa kiểm soát khác.

## 4. Threat model: điều gì có thể xảy ra khi mở nguồn không đáng tin?

Không cần khẳng định một file cụ thể khai thác lỗ hổng đã biết mới phải coi nguồn là nguy hiểm. Các rủi ro cần thiết kế phòng vệ gồm:

| Rủi ro cần xét | Tình huống |
| --- | --- |
| Dữ liệu bị thay đổi/corrupt | File bị cắt, thay byte hoặc không đúng định dạng; việc đọc có thể thất bại hoặc không phản ánh điều đã kỳ vọng |
| Tài nguyên bị tiêu hao | File quá lớn, nhiều sự kiện, metadata phức tạp hoặc stream dài hạn có thể gây tiêu tốn CPU, RAM, I/O |
| Đường dẫn bị điều hướng | Đường dẫn người dùng cung cấp trỏ tới file khác, qua `..`, symbolic link hoặc cơ chế filesystem tương đương |
| Repository có writer không tin cậy | Nội dung/chunk có thể bị thêm, xóa, thay thế trong lúc consumer đang đọc |
| Dữ liệu event bị ứng dụng hiểu sai | Callback dùng field/sự kiện không đúng schema; nội dung event bị đẩy vào log, truy vấn hoặc API không được kiểm soát |
| Rò rỉ dữ liệu quan sát | Recording có thể tiết lộ thông tin nhạy cảm về quá trình chạy; cho phép người dùng đọc không giới hạn cũng là vấn đề quyền truy cập |
| Hành vi callback không an toàn | Callback thực hiện xử lý phức tạp, I/O hoặc ghi log thông tin tùy ý từ event khiến ứng dụng dễ bị ảnh hưởng |

Đây là **những lớp rủi ro cần xét trong thiết kế**, không phải khẳng định rằng mọi file không tin cậy đều khai thác được một lỗi bảo mật cụ thể của JVM. Quy tắc gốc vẫn là: **đừng gửi dữ liệu không đáng tin vào API mà tài liệu yêu cầu nguồn tin cậy**.

Với những luồng nghiệp vụ **bắt buộc** nhận file JFR do bên ngoài cung cấp, không nên trực tiếp đưa chúng cho consumer có quyền cao. Cần một **quy trình nhập dữ liệu riêng** đã được đánh giá bảo mật: kiểm soát nguồn, phân quyền, cách ly, hạn mức tài nguyên và chính sách giữ lại dữ liệu. Không có một lệnh `normalize()` hoặc một bước kiểm tra đuôi file có thể biến mọi recording ngoài thành dữ liệu an toàn để parse.

## 5. Chương trình Java 17+ số 1: tự tạo recording và mở lại file do chính chương trình tạo

Trong ví dụ này:

- Chính tiến trình Java tạo một thư mục và file thử nghiệm.
- `jdk.jfr.Recording` ghi một event tự định nghĩa.
- `recording.dump(ownFile)` xuất file JFR.
- `EventStream.openFile(ownFile)` đọc **chính file vừa được tạo**.
- Callback theo tên xác minh field `sequence=7`.
- `try-with-resources` đóng cả recording lẫn stream; phần `finally` dọn file demo.

Tạo file **`TrustedJfrFileDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class TrustedJfrFileDemo {
    @Name("lesson.TrustedInput")
    static class TrustedInput extends Event {
        int sequence;
    }

    public static void main(String[] args) throws Exception {
        Path ownDirectory = Files.createTempDirectory("jfr-owned-demo-");
        Path ownFile = ownDirectory.resolve("created-locally.jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(TrustedInput.class).withoutThreshold();
                recording.start();

                TrustedInput event = new TrustedInput();
                event.sequence = 7;
                event.commit();

                recording.stop();
                recording.dump(ownFile);
            }

            AtomicInteger received = new AtomicInteger();
            AtomicReference<Throwable> callbackFailure = new AtomicReference<>();

            try (EventStream stream = EventStream.openFile(ownFile)) {
                stream.onEvent("lesson.TrustedInput", event -> {
                    if (event.getInt("sequence") != 7) {
                        throw new AssertionError("Unexpected sequence");
                    }
                    received.incrementAndGet();
                });
                stream.onError(callbackFailure::set);
                stream.start();
            }

            if (callbackFailure.get() != null) {
                throw new AssertionError(
                        "Callback failed", callbackFailure.get());
            }
            if (received.get() != 1) {
                throw new AssertionError(
                        "Unexpected count " + received.get());
            }
            System.out.println("recordingOwnedByThisProcess=true");
            System.out.println("trustedEvents=" + received.get());
            System.out.println("verifiedSequence=7");
        } finally {
            Files.deleteIfExists(ownFile);
            Files.deleteIfExists(ownDirectory);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+ có JFR:

~~~bash
javac --release 17 -encoding UTF-8 TrustedJfrFileDemo.java
java TrustedJfrFileDemo
~~~

**Stdout đã kiểm thử trên Java 17:**

~~~text
recordingOwnedByThisProcess=true
trustedEvents=1
verifiedSequence=7
~~~

### Giải thích tính tin cậy của ví dụ

**Nguồn xuất phát:** file được tạo từ `Recording` mà code đang điều khiển; nó **không** phải một file nhận từ upload hoặc một đường dẫn tùy ý ở request. Việc thử nghiệm này minh họa cách xây dựng nguồn dữ liệu có thể truy xuất được **nguồn gốc**.

**Giới hạn của demo:** `Files.createTempDirectory(...)` ở đây nhằm tạo file thử và dọn dẹp tự động, không phải khuyến nghị rằng **mọi thư mục tạm** đều là vùng lưu trữ tin cậy trong production. Tùy hệ điều hành, ACL/quyền thư mục, tài khoản chạy và tiến trình khác, mức bảo vệ phải được đánh giá riêng. Với hệ thống thật, chọn thư mục do dịch vụ quản lý với quyền truy cập phù hợp.

**`Recording.dump(ownFile)`** tạo recording từ dữ liệu của chính tiến trình, còn **`EventStream.openFile(...)`** đưa recording đó vào bộ đọc. Bởi vậy ta biết ai tạo file và thời điểm sử dụng. `onEvent("lesson.TrustedInput", ...)` chỉ xử lý loại custom event đã định nghĩa. `stream.start()` chạy đồng bộ đến hết file; sau đó chương trình kiểm tra số lượng và field.

**`onError(...)`** thu nhận lỗi trong callback xử lý stream, giúp các lỗi của callback được báo rõ, thay vì im lặng nhìn một số đếm thiếu. Chương trình cũng kiểm tra `received == 1` và ném `AssertionError` nếu không khớp.

**Không được diễn dịch sai:** việc ví dụ này chạy thành công **không chứng minh** bất kỳ file `.jfr` bất kỳ cũng an toàn. Nó chỉ chứng minh một quy trình **tạo → ghi → dump → mở → kiểm tra** với nguồn thử nghiệm tự kiểm soát.

## 6. Không nhận đường dẫn tùy ý: dùng định danh đã phê duyệt

Trong một ứng dụng nhận request như:

~~~text
GET /recordings/view?id=baseline
~~~

một thiết kế tốt hơn `GET /recordings/view?path=/arbitrary/location/file.jfr` là:

1. Caller gửi **định danh logic** như `baseline` hoặc `incident`.
2. Server đối chiếu định danh đó với **danh sách được phê duyệt**.
3. Server tự ánh xạ định danh sang tên file đã biết trong **thư mục đã được vận hành kiểm soát**.
4. Server kiểm tra quyền truy cập của caller vào recording cụ thể.
5. Chỉ sau đó mới gọi consumer đối với nội dung file hợp lệ trong vùng tin cậy.

Điều này **không tự động bảo đảm file an toàn**; nó chỉ ngăn một lớp rủi ro rất quan trọng: client tự điều khiển đường dẫn thô. Trust vẫn cần được thiết lập ở hệ thống tệp và quy trình tạo file.

### Chương trình Java 17+ số 2: giới hạn lựa chọn file bằng allowlist

Tạo file **`ApprovedRecordingSelectionDemo.java`**:

~~~java
import java.nio.file.Path;

public class ApprovedRecordingSelectionDemo {
    static Path approvedFile(Path operatorOwnedDirectory, String id) {
        String name = switch (id) {
            case "baseline" -> "baseline.jfr";
            case "incident" -> "incident.jfr";
            default -> throw new IllegalArgumentException(
                    "Unknown recording identifier");
        };
        return operatorOwnedDirectory.resolve(name);
    }

    public static void main(String[] args) {
        Path configuredRoot = Path.of("operator-owned-jfr").toAbsolutePath();
        System.out.println("baselineFile="
                + approvedFile(configuredRoot, "baseline").getFileName());
        System.out.println("incidentFile="
                + approvedFile(configuredRoot, "incident").getFileName());

        String[] unapproved = {
                "../external.jfr",
                "uploaded.jfr",
                "/tmp/other.jfr"
        };
        int rejected = 0;
        for (String id : unapproved) {
            try {
                approvedFile(configuredRoot, id);
                throw new AssertionError("Should be rejected: " + id);
            } catch (IllegalArgumentException expected) {
                rejected++;
            }
        }
        System.out.println("rejectedUnapprovedIds=" + rejected);
        System.out.println("configuredRootIsAbsolute="
                + configuredRoot.isAbsolute());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ApprovedRecordingSelectionDemo.java
java ApprovedRecordingSelectionDemo
~~~

**Stdout đã kiểm tra:**

~~~text
baselineFile=baseline.jfr
incidentFile=incident.jfr
rejectedUnapprovedIds=3
configuredRootIsAbsolute=true
~~~

**Ý nghĩa và giới hạn:**

- Client chỉ có thể gửi hai **ID** `baseline` hoặc `incident`. Các giá trị dạng traversal `../external.jfr` hoặc đường dẫn tùy ý không phải ID hợp lệ, nên bị **từ chối trước khi mở file**.
- `operatorOwnedDirectory` là một **tham số mà trong hệ thống thật phải do cấu hình tin cậy của server cung cấp**, không phải từ request của người dùng.
- `Path.of("operator-owned-jfr").toAbsolutePath()` trong demo chỉ tạo đường dẫn tuyệt đối để minh họa API. Kết quả `configuredRootIsAbsolute=true` **không chứng minh** thư mục thực sự do operator sở hữu, file tồn tại, quyền được khóa chặt hoặc nội dung file là tin cậy.
- Chương trình này **không thực hiện `EventStream.openFile()`**, vì nó chỉ kiểm thử lớp **chọn đúng file được phép**, không pretend rằng file demo có sẵn. Ví dụ mở/đọc file hoàn chỉnh nằm ở phần 5.
- Trong production, cần kiểm tra thêm danh tính và quyền caller, quyền sở hữu file, provenance, integrity, hệ thống tệp và trạng thái file có thể bị thay thế. Allowlist đường dẫn là một lớp bảo vệ chứ không phải toàn bộ chính sách.

Một đoạn tích hợp **minh họa trong service**, với `id` đã được xác thực quyền và `configuredTrustedRoot` là thư mục đã được quản trị:

~~~java
Path selected = approvedFile(configuredTrustedRoot, id);
try (EventStream stream = EventStream.openFile(selected)) {
    stream.onEvent(event -> handleEvent(event));
    stream.start();
}
~~~

`handleEvent` trong đoạn này là hàm ứng dụng **chưa định nghĩa**. Quan trọng hơn, code giả định bước xác thực **nguồn tin cậy của file** đã được triển khai ngoài method này; không được sao chép nó thành endpoint public bỏ qua kiểm tra quyền và nguồn.

## 7. Vì sao chỉ kiểm tra `Path.normalize()`, extension hoặc kích thước chưa đủ?

### 7.1. `normalize()` là xử lý đường dẫn, không phải kiểm tra người ghi file

Ví dụ:

~~~java
Path normalized = incoming.normalize();
~~~

`normalize()` loại các thành phần dư thừa như `.` hoặc `..` ở mức cú pháp. Nó **không chứng minh** file thuộc quyền quản lý của server, không xác thực nơi file được tạo và không loại được tất cả tác động của symbolic links hoặc cơ chế liên kết ở filesystem.

Ngay cả khi `path.startsWith(trustedRoot)` trả `true` ở mức cấu trúc, nếu một thành phần đường dẫn có thể trỏ tới vùng khác hoặc bị thay thế giữa lúc kiểm tra và mở file, trust boundary vẫn có thể bị phá. Không nên coi so sánh tiền tố chuỗi bằng `startsWith("/opt/jfr")` là một ranh giới bảo mật; nó còn có lỗi khớp tên tương tự `/opt/jfr-backup`.

### 7.2. Kiểm tra mở file và sử dụng file có thể cách nhau về thời gian

Quy trình ngây thơ:

~~~text
1. Kiểm tra path thuộc vùng cho phép
2. Gọi Files.isRegularFile(path)
3. Một tiến trình khác thay file / thay link
4. Gọi EventStream.openFile(path)
~~~

Đây là tình huống **time-of-check to time-of-use (TOCTOU)**. Nếu một principal không tin cậy có quyền sửa file hoặc thư mục cha, việc kiểm tra trước không bảo đảm nội dung được mở sau đó vẫn là nội dung đã kiểm.

Giải pháp thực tế phải dựa trên **quyền sở hữu và quyền ghi của filesystem**, vùng lưu không cho tác nhân không tin cậy thay thế, kiểm soát quá trình upload/copy, và cơ chế mở/đọc được thiết kế phù hợp với threat model. Không có một `Files.isReadable(...)` hay `Path.normalize()` đơn lẻ nào loại bỏ hoàn toàn race.

### 7.3. Dung lượng và checksum là phòng vệ bổ sung

Một giới hạn file size có thể hỗ trợ **quản lý tài nguyên**, nhưng kích thước nhỏ không đồng nghĩa parser input an toàn. Hash/checksum có ích để kiểm tra **tính toàn vẹn** chỉ khi expected digest đến từ **nguồn tin cậy độc lập** (ví dụ manifest xác thực do hệ thống vận hành phát hành). Nếu attacker tạo cả file và checksum thì phép so khớp không chứng minh sự đáng tin.

Ngược lại, một file có checksum đúng vẫn có thể chứa **dữ liệu nhạy cảm** hoặc event values khiến xử lý downstream phải kiểm soát. Integrity là một thành phần của trust, không phải mọi khía cạnh của trust.

## 8. Repository cần ranh giới tin cậy bền vững hơn vì có thể được cập nhật

Đối với:

~~~java
EventStream.openRepository(trustedRepositoryPath)
~~~

API sẽ đọc từ **disk repository JFR**, theo mặc định bắt đầu với event được flush tiếp theo. Nếu đang có một JVM ghi các chunk vào repository, dữ liệu có thể xuất hiện sau khi stream khởi động. Vì vậy:

- Chỉ cấu hình `trustedRepositoryPath` từ **nguồn quản trị đáng tin**.
- Chỉ cho phép JVM/tiến trình đã ủy quyền ghi/chỉnh sửa chunk trong vùng repository.
- Không trỏ tới thư mục upload, thư mục chia sẻ có nhiều người không tin cậy ghi, hoặc directory được đặt trong location mà caller bên ngoài có thể sửa.
- Không coi một repository là một “thư mục JFR bất kỳ”. Nội dung và vòng đời chunk cần được tạo/quản lý bởi JFR.
- Theo dõi lỗi đọc, dung lượng lưu trữ, vòng đời stream và các thay đổi quyền truy cập.
- Đóng `EventStream` và xử lý lỗi khi dịch vụ dừng hoặc cấu hình nguồn không còn hợp lệ.

Cách **mở repository của JVM hiện tại** không có đường dẫn đầu vào:

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.start();
}
~~~

Đây là **đoạn minh họa**, không phải chương trình hữu hạn có `main`. `start()` có thể chặn để chờ các event tiếp theo; cần có chiến lược dừng/đóng stream thích hợp. Việc có `onEvent("jdk.GarbageCollection", ...)` không tự bật JFR event đó. Với theo dõi chính JVM hiện tại, cũng có thể cân nhắc `RecordingStream` nếu muốn vừa cấu hình ghi vừa tiêu thụ các sự kiện đang chạy.

**Không suy luận:** `openRepository()` không tham số **loại bỏ mọi rủi ro**. Nó chỉ tránh việc caller tự chọn một directory bên ngoài; ứng dụng vẫn cần giới hạn quyền ai được gọi API, quản trị repository của JVM, bảo vệ thông tin thu thập được và xử lý event values cẩn thận.

### Chọn `openFile` hay `openRepository`?

| Nhiệm vụ | Lựa chọn |
| --- | --- |
| Phân tích recording đã xuất và được phê duyệt | `EventStream.openFile(trustedFile)` |
| Theo dõi repository đang được ghi bởi một hệ thống đáng tin | `EventStream.openRepository(approvedDirectory)` |
| Theo dõi repository của JVM hiện tại, không nhận path bên ngoài | `EventStream.openRepository()` |
| Ứng dụng tự cấu hình và nhận JFR event của JVM hiện tại | Cân nhắc `RecordingStream` với `enable(...)` và `onEvent(...)` |
| File `.jfr` người dùng lạ vừa tải lên | **Không mở trực tiếp** trong tiến trình privileged; chuyển qua quy trình đánh giá/nhập dữ liệu bảo mật riêng |

## 9. Bảo vệ tài nguyên và dữ liệu trong callback

Ngay cả khi recording đến từ nguồn đã phê duyệt, một hệ thống robust vẫn cần tránh những lỗi vận hành:

**Giới hạn tài nguyên.** Xác định số lượng file, dung lượng, thời gian xử lý, số stream đồng thời và khả năng chịu tải. Với live repository, có chiến lược đóng stream khi kết thúc phiên quan sát. Một recording lớn có thể chứa rất nhiều event; không nạp toàn bộ vào RAM chỉ để đếm một loại sự kiện nếu có thể xử lý theo stream.

**Lọc theo loại event.** Nếu chỉ quan tâm `jdk.CPULoad`, dùng:

~~~java
stream.onEvent("jdk.CPULoad", event -> {
    // Xử lý dữ liệu cần thiết cho báo cáo CPU.
});
~~~

Đây là mã minh họa với biến `stream` có sẵn. Việc đăng ký theo tên có thể giúp tránh gọi callback tổng quát cho những loại không liên quan; tuy nhiên nó **không biến file không tin cậy thành dữ liệu an toàn**, vì parser vẫn phải làm việc với nguồn.

**Không dùng event values làm input đặc quyền trực tiếp.** Tên thread, class, stack frame hoặc custom fields có thể chứa chuỗi do ứng dụng đưa vào JFR. Nếu đưa chúng sang SQL, HTML, log, lệnh shell hoặc API, cần xử lý theo đúng ngữ cảnh đầu ra (parameterized SQL, escaping, phân quyền...). Không tin tưởng các trường chỉ vì chúng xuất hiện trong một recording.

**Thông tin nhạy cảm.** Recording có thể chứa dữ liệu hoạt động nội bộ; giới hạn người được đọc, nơi lưu, thời gian giữ và quyền chia sẻ. Không trả nguyên recording hoặc stack traces cho người không có quyền chỉ vì đọc được bằng API.

**Xử lý lỗi.** `openFile`/`openRepository` có thể gây `IOException` do I/O hoặc không mở được nguồn; callback có thể gặp lỗi theo dữ liệu/schema. Ghi log đủ thông tin để điều tra nhưng tránh tiết lộ đường dẫn nhạy cảm và nội dung không được phép. `IOException` không phải bộ phân loại “đầu vào độc hại” đáng tin; nguồn đáng tin bị hỏng đĩa cũng có thể lỗi, còn đầu vào không tin cậy có thể không gây lỗi rõ ràng.

**Lifecycle.** Ưu tiên try-with-resources. Với `startAsync()`, callback chạy bất đồng bộ: dùng cấu trúc thread-safe khi chia sẻ trạng thái và cơ chế chờ/dừng phù hợp; không dựa vào `Thread.sleep(100)` để kết luận đã đọc đủ file.

## 10. Quy trình xét duyệt nguồn trong ứng dụng

Một luồng triển khai có thể chia thành các cổng kiểm tra:

| Bước | Kiểm tra bắt buộc của hệ thống |
| --- | --- |
| 1. Xác nhận nguồn | Chỉ nhận recording từ tiến trình/đơn vị đã được ủy quyền, hoặc quy trình import riêng |
| 2. Quyền người đọc | User/service có được phép xem recording này và những dữ liệu trong đó không? |
| 3. Chọn định danh | Dùng ID từ allowlist/config/metadata server-side; không nhận raw path ngoài kiểm soát |
| 4. Kiểm soát lưu trữ | Directory, file ownership/ACL, quyền ghi và khả năng thay thế đường dẫn được quản trị |
| 5. Kiểm tra integrity khi cần | Xác thực manifest/signature hoặc digest do nguồn đáng tin cung cấp, không chỉ tính hash tự gửi |
| 6. Giới hạn tài nguyên | Dung lượng, số event, thời gian và số stream đồng thời phù hợp hạ tầng |
| 7. Mở stream | Chỉ khi đạt yêu cầu tin cậy mới gọi `openFile` hoặc `openRepository` |
| 8. Tiêu thụ an toàn | Callback ngắn gọn; kiểm tra schema/field, tách dữ liệu untrusted khỏi thao tác nguy hiểm |
| 9. Đóng/ghi nhận lỗi | `close()`/try-with-resources; log có phân quyền, metric vận hành, dọn tài nguyên |

**Bước 1 và bước 4 là cốt lõi.** Việc quét extension, gọi `normalize()`, kiểm tra `Files.isReadable` hoặc chạy parser thử nghiệm **không** thể thay thế xác định **ai có quyền tạo và thay đổi nội dung được mở**.

Nếu một sản phẩm phải nhận JFR từ người dùng bên ngoài, đó là nhu cầu sản phẩm khác với đọc trusted JFR. Cần thiết kế môi trường import hạn chế quyền, đánh giá rủi ro bộ parser của các JDK đang dùng, áp dụng kiểm soát thời gian/tài nguyên và chỉ quảng bá kết quả đã được sàng lọc. Không coi ví dụ demo mở file tự tạo là mẫu endpoint để đọc upload công khai.

## 11. Các lỗi phổ biến

1. **“Có đuôi `.jfr` là tin cậy.”** Sai. Extension chỉ là một phần tên file, không phải chữ ký nguồn hoặc bảo đảm an toàn.
2. **“`openFile` chạy không ném lỗi nghĩa là file an toàn.”** Sai. Parse thành công không xác thực ai tạo/chỉnh sửa file.
3. **“`Path.normalize()` và `startsWith` chặn mọi chuyển hướng đường dẫn.”** Sai nếu nguồn/dir còn bị thay đổi, symlink/junction hoặc kiểm tra không đúng ngữ nghĩa filesystem.
4. **“Chỉ cần xác nhận file nhỏ.”** Sai. Giới hạn size giúp giảm rủi ro tài nguyên, không xác thực nguồn và không chống mọi input bất thường.
5. **“File và SHA-256 đều do người gửi cung cấp nên nguồn đã tin cậy.”** Sai. Hash chỉ hữu ích xác thực khi giá trị kỳ vọng được lấy từ kênh tin cậy độc lập.
6. **“`openRepository(Path)` có thể trỏ thẳng vào thư mục upload để tiện theo dõi.”** Không phù hợp với khuyến cáo API. Repository phải là vùng lưu JFR do nguồn tin cậy quản trị.
7. **“`openRepository()` không có tham số luôn an toàn tuyệt đối.”** Sai. Nó tránh path ngoài, nhưng vẫn phụ thuộc môi trường JVM, quyền truy cập và cách xử lý dữ liệu thu được.
8. **“Cứ catch `IOException` là xong vấn đề bảo mật.”** Sai. Catch giúp xử lý lỗi mở/đọc, không thể chứng nhận integrity hoặc trust của nguồn.
9. **“Có thể cho mọi user xem recording, vì JFR chỉ là metric.”** Sai. Event có thể chứa thông tin hoạt động, method/class names, stack traces hoặc dữ liệu custom nhạy cảm.
10. **“Có thể xử lý mọi event field như chuỗi an toàn.”** Sai. Các field đến từ dữ liệu có thể được ứng dụng cung cấp; validate/escape theo nơi sử dụng.
11. **“Kiểm tra file một lần là đủ dù nơi lưu trữ có writer không tin cậy.”** Sai. File/repository có thể bị thay đổi giữa bước kiểm tra và bước đọc, đặc biệt với live repository.
12. **“Thêm `onEvent("name", ...)` khiến nguồn ngoài trở thành an toàn.”** Sai. Nó chỉ lọc những event được callback xử lý, không phải cơ chế xác thực recording.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Tài liệu `EventStream.openFile(Path)` đưa ra nguyên tắc nào về nguồn?  
**Đáp án:** Chỉ nên mở **JFR recording files từ nguồn tin cậy**.

**Câu 2.** Khác biệt về tin cậy giữa `openRepository()` và `openRepository(Path)` là gì?  
**Đáp án:** Cái đầu dùng repository của JVM hiện tại mà không nhận path; cái sau nhận đường dẫn disk repository cụ thể, nên phải bảo đảm directory đó được quản trị bởi nguồn tin cậy. Cả hai vẫn cần phân quyền sử dụng và quản lý nội dung.

**Câu 3.** Client gửi `?path=../../unrelated.jfr`. Có nên nối path vào thư mục chính rồi gọi `openFile` sau `normalize()` không?  
**Đáp án:** Không. Nên tránh cho client điều khiển path thô; dùng ID cho các recording được phê duyệt từ cấu hình/metadata server và kiểm soát filesystem.

**Câu 4.** Kiểm tra `Files.isRegularFile(path)` chứng minh recording an toàn chưa?  
**Đáp án:** Chưa. Nó kiểm tra loại đối tượng filesystem, không xác thực nguồn hoặc quyền của người có thể thay nội dung.

**Câu 5.** Có thể dựa vào hash do chính người tải file gửi kèm để chứng minh provenance không?  
**Đáp án:** Không. Muốn dùng hash để xác thực integrity cần **expected digest từ nguồn tin cậy**; provenance là một hợp đồng rộng hơn.

**Câu 6.** Nếu stream đang đọc repository và một tài khoản không tin cậy có quyền ghi chunk, rủi ro chính là gì?  
**Đáp án:** Nội dung được tiêu thụ có thể thay đổi trong lúc stream chạy; repository không còn bảo đảm là vùng lưu tin cậy.

**Câu 7.** Trong ví dụ `TrustedJfrFileDemo`, nguồn recording đến từ đâu?  
**Đáp án:** Chính code Java tạo event, ghi và dump file rồi mới mở lại; không nhận file ngoài do client chỉ định.

**Câu 8.** Nếu file được phê duyệt nhưng chứa custom field có nội dung nguy hiểm khi đưa ra HTML, có cần escape không?  
**Đáp án:** Có. **Trusted recording provenance** không thay thế việc xử lý an toàn các giá trị khi đưa sang ngữ cảnh khác.

## Tài liệu Java chính thức

- **Oracle Java SE 17 — EventStream:** `openFile(Path)` và `openRepository(Path)` đều cảnh báo chỉ mở nguồn tin cậy; thêm thông tin về cách hoạt động, `IOException`, `start()` và `close()`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- **Oracle Java SE 26 — EventStream:** phiên bản API hiện đại vẫn nêu yêu cầu file recording/repository tin cậy và ba factory methods. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- **Oracle Java SE 17 — Recording:** tạo và dump recording do ứng dụng kiểm soát, dùng trong ví dụ chạy được. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html
- **Oracle Java SE 17 — jdk.jfr.Event:** định nghĩa và commit custom event. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html
- **Oracle Java SE 17 — jdk.jfr.consumer.RecordedEvent:** đọc dữ liệu và metadata của sự kiện từ stream. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- **Dev.java — JFR command / repository:** giải thích dữ liệu JFR được viết thành chunks, repository và cách `jfr assemble` tạo file từ các chunk. https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/
- **Oracle Java SE 17 — Path / Files API:** hiểu giới hạn của `Path.normalize()`, `Files.isRegularFile` và kiểm soát nguồn trên filesystem. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html