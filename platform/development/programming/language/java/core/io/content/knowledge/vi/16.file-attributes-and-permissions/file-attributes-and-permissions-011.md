# `Files.probeContentType(Path)` và giới hạn suy đoán MIME type

## 1. Mục đích và ý nghĩa của MIME type

**MIME type** (*media type*) mô tả kiểu nội dung theo cấu trúc `type/subtype`. Ví dụ: `text/plain` (văn bản thuần), `text/html` (HTML), `image/png` (ảnh PNG), `image/jpeg` (ảnh JPEG), `application/pdf` (PDF), `application/zip` (ZIP). `application/octet-stream` thường được ứng dụng dùng cho dữ liệu nhị phân chưa biết loại cụ thể.

Trong Java NIO.2, `java.nio.file.Files.probeContentType(Path)` trả về **loại nội dung mà môi trường có thể suy đoán** cho một đường dẫn. Nó hữu ích để hiển thị nhãn tệp, hỗ trợ phân loại ban đầu hoặc lựa chọn `Content-Type` khi đã có chính sách xác minh độc lập.

Điểm cần ghi nhớ: **suy đoán MIME không có nghĩa là xác minh định dạng**. MIME type khác với đuôi tệp (`.png`, `.txt`), bộ mã hóa văn bản (UTF-8, UTF-16) và quyền truy cập tệp. Kết quả dò MIME cũng không tự chứng minh tệp tồn tại hay an toàn.

## 2. Hợp đồng API

```java
public static String probeContentType(Path path) throws IOException
```

- **Đối số `path`:** đường dẫn cần dò loại nội dung.
- **Giá trị trả về:** chuỗi MIME, ví dụ `"text/plain"`, hoặc **`null` khi không xác định được**.
- **`IOException`:** có thể xảy ra nếu bộ phát hiện cần truy cập tệp hoặc tài nguyên hệ thống và gặp lỗi I/O.
- **`NullPointerException`:** phát sinh khi truyền `null` làm đường dẫn.
- Phương thức **không hứa** đọc toàn bộ tệp, kiểm tra chữ ký nhị phân hay xác minh tệp hợp lệ.

Theo hợp đồng Java SE, cách dò là *implementation-specific*: bộ dò có thể dùng phần mở rộng, tên tệp, thuộc tính, dữ liệu của hệ điều hành hoặc byte nội dung. Java không quy định một cách dò duy nhất và không bảo đảm MIME cố định trên mọi máy.

**Ví dụ:** Một tệp chứa văn bản nhưng được đặt tên `photo.png` vẫn có thể được bộ dò dựa vào đuôi tên trả về `image/png`. Ngược lại, một tệp hợp lệ nhưng có đuôi lạ có thể trả về `null`.

## 3. Cơ chế phát hiện và yếu tố môi trường

Java có SPI `java.nio.file.spi.FileTypeDetector` để cung cấp bộ phát hiện loại tệp. Các triển khai được cài đặt có thể được nạp qua cơ chế provider/`ServiceLoader`; chúng được thử trước bộ dò mặc định của hệ thống. Thứ tự thử giữa nhiều bộ dò được cài đặt là chi tiết triển khai, vì thế không nên thiết kế ứng dụng phụ thuộc thứ tự ấy.

Mỗi bộ dò tự quyết định cách suy đoán. Có bộ dò dựa trên ánh xạ đuôi tệp của hệ điều hành, có bộ dò kiểm tra dữ liệu khác. Kết quả chịu ảnh hưởng của JDK, hệ điều hành, bộ dò được cài và cấu hình môi trường.

| Câu hỏi | API hoặc cách xử lý phù hợp |
| --- | --- |
| Hệ thống suy đoán MIME nào? | `Files.probeContentType(path)` |
| Đường dẫn có phải tệp thường tại thời điểm kiểm tra? | `Files.isRegularFile(path)` |
| Hiện tại có thể đọc tệp không? | `Files.isReadable(path)` hoặc thử mở tệp |
| Kích thước tệp là bao nhiêu? | `Files.size(path)` |
| Byte đầu có giống chữ ký định dạng? | Đọc các byte thực và so sánh với đặc tả |
| Tệp có được ứng dụng chấp nhận không? | Chính sách loại tệp + parser/decoder + giới hạn tài nguyên |

`Files.isReadable` và `Files.isRegularFile` cũng chỉ kiểm tra trạng thái tại một thời điểm; tệp và quyền có thể thay đổi trước khi thao tác kế tiếp diễn ra (*TOCTOU*). Với dữ liệu quan trọng, phải xử lý lỗi ngay tại thao tác mở và đọc thực tế.

## 4. Ví dụ Java 17+ chạy độc lập

Ví dụ tự tạo tệp tạm có đuôi `.txt`, ghi nội dung UTF-8, dò MIME, xử lý `null` và xóa tệp sau khi dùng.

**`ProbeContentTypeDemo.java`**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ProbeContentTypeDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("mime-demo-", ".txt");
        try {
            Files.writeString(path, "Hello, Java!", StandardCharsets.UTF_8);

            String mime = Files.probeContentType(path);
            if (mime == null) {
                System.out.println("Khong xac dinh duoc MIME type.");
            } else {
                System.out.println("MIME type suy doan: " + mime);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp mã nguồn:

```bash
javac ProbeContentTypeDemo.java
java ProbeContentTypeDemo
```

Một **kết quả có thể gặp** khi môi trường nhận diện đuôi `.txt` là:

```text
MIME type suy doan: text/plain
```

Nếu bộ dò không xác định được loại tệp, stdout là:

```text
Khong xac dinh duoc MIME type.
```

Đây là **hai nhánh có điều kiện**. Không có stdout MIME cố định được bảo đảm xuyên môi trường. `finally` giúp dọn tệp tạm ngay cả khi việc ghi hoặc dò MIME bị lỗi.

Với một `Path file` đã có trong chương trình, có thể sử dụng ngắn gọn:

```java
String mime = Files.probeContentType(file);
String displayType = (mime == null) ? "Chua xac dinh" : mime;
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập; nó vẫn cần xử lý `IOException` tại phương thức gọi. `displayType` chỉ nên là thông tin hiển thị hoặc một gợi ý, không phải điều kiện đủ để chấp nhận tệp tải lên.

## 5. Giới hạn cần nắm vững

### 5.1. Dò MIME không xác thực nội dung

Đổi tên `note.txt` thành `note.png` không biến nội dung thành ảnh. Nếu bộ dò dùng phần mở rộng, kết quả có thể là `image/png` dù toàn bộ byte là văn bản. Các tệp sai đuôi, dữ liệu giả mạo, tệp hỏng, tệp ghép nhiều định dạng (*polyglot*) hoặc phần mở rộng không quen thuộc đều gây rủi ro suy đoán sai.

Không mặc định rằng `Files.probeContentType` đã đọc *magic bytes*. Ngay cả khi bộ dò có đọc vài byte, kiểm tra đó chưa bảo đảm toàn bộ tệp có cấu trúc hợp lệ.

### 5.2. `null` không khẳng định tệp bị hỏng hay không tồn tại

`null` chỉ có nghĩa bộ dò hiện tại **không xác định được MIME type**. Tệp có thể tồn tại, đọc được và hoàn toàn hợp lệ. Nếu nghiệp vụ bắt buộc phải biết định dạng, hãy chuyển sang quy trình xác minh phù hợp hoặc từ chối theo chính sách, thay vì tự gán một MIME nằm trong danh sách được phép.

`application/octet-stream` là fallback hợp lý trong một số ngữ cảnh truyền tải nhị phân, **nhưng không phải kết quả fallback do API này tự động bảo đảm**. Gán MIME fallback là quyết định của ứng dụng.

### 5.3. MIME khác charset, định dạng hợp lệ và quyền truy cập

`text/plain` không xác định nội dung được mã hóa UTF-8 hay UTF-16. Khi đọc văn bản, ứng dụng cần một hợp đồng charset rõ ràng; ví dụ `Files.readString(path, StandardCharsets.UTF_8)` chỉ phù hợp nếu nội dung thực sự sử dụng UTF-8.

MIME không cho biết tệp có quyền đọc/ghi/thực thi hay không. Trạng thái quyền được quản lý bằng cơ chế hệ thống tệp và chính sách ứng dụng. Dựa vào MIME để quyết định quyền thực thi hay truy cập là sai mục đích API.

### 5.4. Môi trường có thể trả kết quả khác nhau

Máy A có thể nhận dạng `.svg` trong khi máy B trả về `null` hoặc một chuỗi khác. Đặc biệt không nên viết kiểm thử cứng rằng `Files.probeContentType` phải trả về cùng MIME trong mọi CI, JDK và hệ điều hành.

Khi cần hành vi bất biến, ứng dụng nên định nghĩa danh sách định dạng hỗ trợ và bộ xác minh riêng. Kiểm thử nên bảo đảm mã xử lý đúng khi nhận MIME hợp lệ, MIME không mong đợi, `null` và `IOException`; kiểm thử cấu trúc tệp nên kiểm thử parser/decoder thay vì hành vi bộ dò của máy.

### 5.5. Không dùng MIME suy đoán làm hàng rào bảo mật

Không chỉ dùng `probeContentType` để chấp nhận upload, cho phép thực thi, mở tệp tự động, giải nén, hay hiển thị HTML/SVG inline trên trình duyệt. HTTP header `Content-Type` do client cung cấp cũng có thể bị giả mạo. Cần đánh giá loại tệp theo nội dung thực tế, ứng dụng xử lý và chính sách an toàn cụ thể.

## 6. Đối chiếu với kiểm tra chữ ký PNG bằng byte thực

PNG có chữ ký cố định ở đầu tệp: `89 50 4E 47 0D 0A 1A 0A` (hex). Chương trình sau đọc đúng tối đa tám byte đầu và đối chiếu chữ ký, **không dựa vào tên hay đuôi tệp**.

**`PngSignatureDemo.java`**

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class PngSignatureDemo {
    private static final byte[] PNG_SIGNATURE = {
        (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
    };

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Cach dung: java PngSignatureDemo <duong-dan>");
            return;
        }

        Path path = Path.of(args[0]);
        try (InputStream input = Files.newInputStream(path)) {
            byte[] prefix = input.readNBytes(PNG_SIGNATURE.length);
            boolean matches = Arrays.equals(prefix, PNG_SIGNATURE);
            System.out.println("Co chu ky PNG: " + matches);
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac PngSignatureDemo.java
java PngSignatureDemo example.png
```

Nếu tệp tồn tại, đọc được và tám byte đầu khớp chữ ký PNG, stdout chính xác là:

```text
Co chu ky PNG: true
```

Nếu tệp đọc được nhưng không khớp chữ ký, stdout là:

```text
Co chu ky PNG: false
```

Nếu tệp quá ngắn, `readNBytes(8)` trả về mảng ít byte hơn và `Arrays.equals` trả về `false`. Nếu không mở hoặc đọc được tệp, chương trình có thể kết thúc bằng `IOException`. Một chữ ký đúng **chưa đủ chứng minh ảnh PNG hợp lệ hoặc an toàn**: cần kiểm tra cấu trúc/giải mã bằng thư viện thích hợp, cùng giới hạn kích thước, bộ nhớ và thời gian xử lý.

## 7. Quy trình phù hợp khi nhận tệp từ nguồn không tin cậy

Giả sử backend cho phép người dùng tải lên ảnh đại diện PNG/JPEG. Có thể triển khai theo thứ tự:

1. **Xác định danh sách cho phép**: chỉ PNG và JPEG; loại khác bị từ chối theo chính sách. Không tin tên tệp do client cung cấp để xây đường dẫn lưu trữ.
2. **Giới hạn dữ liệu trước khi xử lý tốn tài nguyên**: kích thước file upload, số lượng tệp, vị trí lưu, quyền truy cập và ngân sách giải mã.
3. **Dò MIME để tham khảo**: gọi `Files.probeContentType(path)` và xử lý cả `null` lẫn `IOException`; gợi ý MIME không cấp quyền chấp nhận.
4. **Kiểm tra byte và định dạng**: kiểm tra chữ ký, sau đó dùng decoder/parser tin cậy để xác minh tệp đọc được theo định dạng đã cho. Không chỉ kiểm tra phần mở rộng hoặc tám byte đầu.
5. **Áp dụng chính sách xử lý và xuất tệp**: chỉ chấp nhận tệp đã qua các kiểm tra cần thiết; chọn MIME cho phản hồi dựa trên định dạng đã được xác minh. Với nội dung không tin cậy, cân nhắc `Content-Disposition: attachment` và `X-Content-Type-Options: nosniff` khi phục vụ qua HTTP.
6. **Xử lý lỗi và thay đổi trạng thái**: kiểm tra `IOException` ở thao tác I/O thật; tránh dựa vào một lần kiểm tra thuộc tính trước đó nếu tệp có thể bị thay thế.

Kiểm tra định dạng không thay thế quét nội dung độc hại, cô lập môi trường xử lý hoặc cập nhật thư viện giải mã khi tình huống yêu cầu những biện pháp ấy.

## 8. Lỗi thường gặp

| Cách viết hoặc giả định sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `Files.probeContentType(path).equals("image/png")` | `null` gây `NullPointerException` | Viết `"image/png".equals(Files.probeContentType(path))` và xử lý I/O |
| `null` nghĩa là không tồn tại | Chẩn đoán sai | Dùng API truy cập/kiểm tra tồn tại phù hợp |
| `image/png` nghĩa là ảnh PNG hợp lệ | Có thể bị giả mạo bằng phần mở rộng | Kiểm tra byte và giải mã |
| MIME chứa charset | Có thể đọc văn bản sai mã hóa | Đặt quy tắc charset rõ ràng |
| MIME quyết định quyền đọc/ghi | Sai khái niệm | Áp dụng quyền hệ thống tệp/chính sách |
| `isReadable` bảo đảm lần đọc sau thành công | Tệp/quyền có thể đổi giữa hai thao tác | Bắt lỗi tại thao tác I/O thực tế |
| Test bắt buộc `.txt` phải luôn thành `text/plain` | Thất bại trên máy khác | Test nhánh `null`/giá trị không mong đợi; kiểm định riêng |

## 9. Tổng kết

**`Files.probeContentType(Path)` là API suy đoán MIME type, có thể trả về `null` hoặc ném `IOException`.** Cách dò phụ thuộc JDK, hệ điều hành và các bộ phát hiện được cài đặt. Không được suy ra rằng Java luôn mở tệp, đọc magic bytes hay xác minh toàn bộ định dạng. Trong hệ thống I/O, cần phân biệt tên và thuộc tính, khả năng truy cập, nội dung thực tế, tính hợp lệ của định dạng và chính sách nghiệp vụ.

**Tham khảo API:** Java SE 17, `java.nio.file.Files#probeContentType(Path)` và `java.nio.file.spi.FileTypeDetector`.
