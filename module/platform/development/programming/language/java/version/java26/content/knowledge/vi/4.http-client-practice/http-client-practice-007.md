# Tải một vùng tệp bằng `BodyPublishers.ofFileChannel`

Java 26 bổ sung `HttpRequest.BodyPublishers.ofFileChannel(FileChannel, long, long)` để gửi một vùng byte của tệp làm request body. Thay vì tự đọc vùng dữ liệu vào một mảng `byte[]`, ứng dụng mở `FileChannel`, chỉ định vị trí bắt đầu và số byte cần gửi, rồi giao việc phát dữ liệu cho `HttpClient`.

API này hữu ích khi tải lên tệp lớn theo từng phần, gửi lại một phần bị lỗi hoặc gửi nhiều phần của cùng một tệp đồng thời. Một `FileChannel` có thể được dùng chung bởi nhiều `BodyPublisher` cho các vùng khác nhau. Phương thức không thay đổi vị trí hiện tại của channel và không tự đóng channel; ứng dụng phải giữ channel mở đến khi mọi request dùng nó đã hoàn tất. [Java SE 26 Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) · [JEP 517 và cập nhật HTTP Client](https://inside.java/2026/03/04/jdk-26-http-client/).

`ofFileChannel` là API Java SE ổn định được giới thiệu trong Java 26 (`Since: 26`), thuộc module `java.net.http`. API này không phải preview hay incubator; không cần `--enable-preview` hoặc `--add-modules` để sử dụng. Javadoc Java 27 vẫn có phương thức này, vì vậy ví dụ tiếp tục áp dụng trên JDK 27.

## 1. Phương thức nhận những tham số nào?

Chữ ký API:

```java
public static HttpRequest.BodyPublisher ofFileChannel(
        FileChannel channel,
        long offset,
        long length
) throws IOException
```

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `channel` | `FileChannel` đang mở và tham chiếu tới tệp nguồn. | Channel được mở bằng `FileChannel.open(path, StandardOpenOption.READ)`. |
| `offset` | Vị trí byte đầu tiên cần gửi, tính từ đầu tệp và bắt đầu từ `0`. | `offset = 1_048_576` nghĩa là bắt đầu ở byte thứ 1.048.577 theo cách đếm từ 1. |
| `length` | Số byte cần gửi kể từ `offset`. | `length = 2_097_152` nghĩa là gửi 2 MiB. |

Vùng dữ liệu được chọn là khoảng nửa mở `[offset, offset + length)`: byte tại `offset` được gửi, còn byte tại `offset + length` không nằm trong body. Byte cuối cùng được gửi có chỉ số `offset + length - 1` nếu `length` lớn hơn `0`.

Ví dụ, với `offset = 4096` và `length = 1024`, body chứa đúng 1.024 byte có chỉ số từ 4.096 đến 5.119. Các giá trị là số byte, không phải ký tự, số dòng hoặc vị trí của một `CharBuffer`.

`offset` được tính từ đầu tệp, không phụ thuộc `channel.position()`. Nếu trước đó gọi `channel.position(500)`, `ofFileChannel(channel, 4096, 1024)` vẫn chọn vùng bắt đầu tại byte 4.096. Javadoc cũng cam kết phương thức và `BodyPublisher` trả về không thay đổi vị trí hiện tại của channel.

## 2. Chọn `ofFileChannel` hay publisher khác?

Các factory trong `HttpRequest.BodyPublishers` giải quyết những nguồn request body khác nhau:

| Publisher | Nguồn dữ liệu | Dùng khi |
|---|---|---|
| `ofFile(Path)` | Toàn bộ nội dung của một tệp theo đường dẫn. | Muốn gửi cả tệp và không cần tự quản lý `FileChannel`. |
| `ofFileChannel(channel, offset, length)` | Một vùng byte của tệp đang mở. | Muốn gửi một phần tệp, chia tệp thành các phần hoặc gửi nhiều phần đồng thời. |
| `ofByteArray(bytes)` | Mảng byte đã có trong bộ nhớ. | Body đã nhỏ và đang có sẵn dưới dạng `byte[]`. |
| `ofInputStream(supplier)` | Dữ liệu đọc từ `InputStream` do supplier cung cấp. | Nguồn dữ liệu là stream hoặc được tạo theo từng lần subscribe. |

`ofByteArray` đòi hỏi ứng dụng có sẵn mảng chứa dữ liệu; việc đọc cả tệp lớn vào một mảng có thể làm tăng mạnh bộ nhớ sử dụng và bị giới hạn bởi kích thước mảng. `ofFile(Path)` phù hợp khi gửi toàn bộ tệp. `ofFileChannel` cho phép chọn chính xác một vùng byte mà không cần tự gom vùng đó thành một mảng lớn.

Không nên suy ra rằng `ofFileChannel` bảo đảm zero-copy hoặc bỏ qua mọi lần sao chép trong hệ điều hành và network stack. Cam kết API là publisher đọc đúng vùng byte được chỉ định từ `FileChannel`; chi tiết tối ưu I/O phụ thuộc implementation và nền tảng.

## 3. Gửi một vùng tệp trong request đồng bộ

Ví dụ sau gửi một phần của tệp tới endpoint nhận một phần upload. Endpoint và cách đặt tên phần là quy ước của dịch vụ nhận; `ofFileChannel` chỉ tạo request body từ vùng byte đã chọn, không tự tạo giao thức upload theo chunk.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class UploadFileRegion {
    public static void main(String[] args) throws IOException, InterruptedException {
        Path file = Path.of("large-video.bin");
        URI uploadUri = URI.create(
                "https://upload.example.com/uploads/42/parts/0"
        );

        long offset = 8L * 1024 * 1024;  // Bắt đầu tại 8 MiB
        long length = 4L * 1024 * 1024;  // Gửi 4 MiB

        HttpClient client = HttpClient.newHttpClient();

        // Channel được giữ mở cho tới khi client.send hoàn tất.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ
        )) {
            long fileSize = channel.size();
            validateRange(fileSize, offset, length);

            HttpRequest.BodyPublisher body =
                    HttpRequest.BodyPublishers.ofFileChannel(
                            channel,
                            offset,
                            length
                    );

            HttpRequest request = HttpRequest.newBuilder(uploadUri)
                    .header("Content-Type", "application/octet-stream")
                    .PUT(body)
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IOException(
                        "Upload failed: HTTP " + response.statusCode()
                                + ", body=" + response.body()
                );
            }

            System.out.println("Uploaded bytes: " + length);
            System.out.println("Server response: " + response.statusCode());
        }
    }

    private static void validateRange(
            long fileSize,
            long offset,
            long length
    ) {
        if (offset < 0 || length < 0
                || offset > fileSize
                || length > fileSize - offset) {
            throw new IndexOutOfBoundsException(
                    "Invalid file range: offset=" + offset
                            + ", length=" + length
                            + ", fileSize=" + fileSize
            );
        }
    }
}
```

`validateRange` dùng phép so sánh `length > fileSize - offset` sau khi xác nhận `offset <= fileSize`. Cách viết này tránh cộng `offset + length` trước khi kiểm tra, vì phép cộng hai số `long` có thể tràn. Bản thân `ofFileChannel` cũng kiểm tra vùng byte so với kích thước tệp và ném `IndexOutOfBoundsException` nếu vùng nằm ngoài tệp.

`try-with-resources` phù hợp với ví dụ đồng bộ vì `client.send(...)` chỉ trả về sau khi request đã được gửi và response body handler hoàn tất. Channel được đóng sau đó. `ofFileChannel` không đóng channel thay ứng dụng.

Phương thức `PUT` trong ví dụ là lựa chọn theo hợp đồng endpoint minh họa. Nếu server yêu cầu `POST`, hãy dùng `.POST(body)`. Body publisher không quyết định phương thức HTTP, đường dẫn, mã phần, cách ghép các phần hoặc cách xác nhận upload.

## 4. Kiểm tra vùng byte trước khi gửi

Để tránh gửi nhầm dữ liệu hoặc tạo request chắc chắn thất bại, cần xác minh các điều kiện:

- `offset` không âm.
- `length` không âm.
- `offset` không lớn hơn kích thước tệp.
- `length` không lớn hơn `fileSize - offset`.
- `FileChannel` còn mở và kích thước tệp có thể xác định được.

API ném các ngoại lệ sau theo hợp đồng:

| Ngoại lệ | Trường hợp |
|---|---|
| `IndexOutOfBoundsException` | Vùng `[offset, offset + length)` vượt ngoài kích thước tệp hoặc có chỉ số không hợp lệ. |
| `IOException` | Không xác định được kích thước channel hoặc channel đã đóng. Việc mở tệp và gửi request cũng có thể phát sinh `IOException`. |

`length = 0` biểu thị body rỗng. `HttpRequest.BodyPublisher` có thể báo độ dài `0`; theo hợp đồng của `BodyPublisher`, HTTP Client có thể không subscribe publisher vì không có dữ liệu cần gửi. Với upload theo phần, thông thường chỉ tạo request cho các vùng có `length > 0`; xử lý tệp rỗng theo hợp đồng riêng của API upload. Trong ví dụ chia phần, tệp có kích thước `0` sẽ không tạo request phần nào; nếu server cần ghi nhận tệp rỗng, ứng dụng phải gọi luồng khởi tạo/hoàn tất phù hợp.

Không tự đặt header `Content-Length`. Publisher biết độ dài body từ `length`, và HTTP Client chịu trách nhiệm biểu diễn body theo giao thức. Tự đặt header này có thể bị từ chối vì đây là header bị hạn chế trong cấu hình mặc định của HTTP Client.

## 5. Gửi nhiều vùng của cùng một tệp đồng thời

Một ứng dụng có thể chia tệp thành các phần có kích thước cố định rồi gửi mỗi phần bằng một request riêng. Javadoc nêu rõ cách dùng điển hình: mở một `FileChannel`, tạo nhiều `BodyPublisher` từ cùng channel với các cặp `offset` và `length` khác nhau, thường là các vùng không chồng lấn, rồi gửi các request đồng thời.

Ví dụ dưới đây dùng endpoint giả định `/parts/{partNumber}`. Server phải biết cách lưu từng phần và ghép chúng theo đúng thứ tự khi hoàn tất upload.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class ConcurrentChunkUpload {
    public static void upload(
            HttpClient client,
            Path file,
            URI uploadBaseUri,
            long chunkSize
    ) throws IOException {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        // Channel chỉ được đóng sau khi tất cả request đã hoàn tất.
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ
        )) {
            long fileSize = channel.size();
            List<CompletableFuture<HttpResponse<Void>>> uploads =
                    new ArrayList<>();

            long offset = 0;
            long partNumber = 0;

            while (offset < fileSize) {
                long length = Math.min(chunkSize, fileSize - offset);
                long currentPart = partNumber;

                URI partUri = URI.create(
                        uploadBaseUri.toString() + "/parts/" + currentPart
                );

                HttpRequest request = HttpRequest.newBuilder(partUri)
                        .header("Content-Type", "application/octet-stream")
                        .PUT(HttpRequest.BodyPublishers.ofFileChannel(
                                channel,
                                offset,
                                length
                        ))
                        .build();

                uploads.add(client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                ));

                offset += length;
                partNumber++;
            }

            // Chờ toàn bộ request xong trước khi try-with-resources đóng channel.
            CompletableFuture.allOf(
                    uploads.toArray(CompletableFuture<?>[]::new)
            ).join();

            for (int i = 0; i < uploads.size(); i++) {
                HttpResponse<Void> response = uploads.get(i).join();
                if (response.statusCode() < 200 || response.statusCode() >= 300) {
                    throw new IOException(
                            "Part " + i + " failed with HTTP "
                                    + response.statusCode()
                    );
                }
            }
        }
    }
}
```

Điểm quan trọng của ví dụ:

1. Mỗi phần có một `BodyPublisher` riêng, nhưng các publisher dùng chung `FileChannel`.
2. Các vùng byte không chồng lấn: phần kế tiếp bắt đầu tại `offset + length` của phần trước.
3. Dùng `sendAsync` để các request có thể chạy đồng thời.
4. `CompletableFuture.allOf(...).join()` đợi tất cả request hoàn tất trước khi khối `try` đóng channel.
5. Kiểm tra status code từng phần; `allOf` hoàn tất bình thường chỉ cho biết các future không kết thúc exceptional, không tự khẳng định server trả status 2xx.

Ví dụ giả định server hỗ trợ upload từng phần tại endpoint tương ứng. Hệ thống thực tế còn cần API khởi tạo upload, định danh upload, lưu mã phần, xác nhận phần đã nhận, xử lý phần gửi lại và lệnh hoàn tất để ghép tệp. Nếu một phần thất bại, không được coi toàn bộ tệp đã upload thành công.

### Quản lý channel khi dùng `sendAsync`

Không viết đoạn sau:

```java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    HttpRequest request = HttpRequest.newBuilder(uri)
            .PUT(HttpRequest.BodyPublishers.ofFileChannel(channel, 0, channel.size()))
            .build();

    // Sai: channel bị đóng khi rời khỏi khối try, trong khi request có thể
    // vẫn đang đọc body ở một thread khác.
    client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
}
```

`sendAsync` trả về ngay một `CompletableFuture`; request có thể chưa đọc xong body tại thời điểm phương thức trả về. Nếu đóng channel ngay sau đó, publisher có thể không đọc được dữ liệu cần gửi. Hãy giữ tham chiếu channel đến khi future hoàn tất, hoặc đợi tất cả future hoàn tất trước khi đóng như ví dụ upload nhiều phần ở trên.

## 6. Những điều API không tự làm

`ofFileChannel` chỉ tạo request body từ một vùng tệp. Ứng dụng và server vẫn phải thống nhất giao thức upload.

| API không tự làm | Trách nhiệm của ứng dụng/server |
|---|---|
| Không tự chia tệp thành nhiều HTTP request. | Tính `offset`, `length`, số phần và tạo request tương ứng. |
| Không tự thêm `Content-Range`, số thứ tự phần hoặc upload ID. | Đưa metadata theo đúng hợp đồng endpoint; mỗi dịch vụ có thể dùng path, query hoặc header riêng. |
| Không tự ghép các phần ở server. | Server lưu phần, kiểm tra đủ phần và ghép đúng thứ tự. |
| Không tự triển khai retry/resume hoặc đảm bảo idempotency. | Thiết kế mã phần ổn định, cơ chế xác nhận và retry an toàn. |
| Không tự kiểm tra hash của tệp hoặc phần. | Tính checksum nếu giao thức upload yêu cầu và xác minh ở server. |
| Không đóng `FileChannel`. | Giữ channel mở trong toàn bộ thời gian publisher có thể đọc và đóng đúng lúc. |

Không nhầm `ofFileChannel` với HTTP `Range` header. `Range` thường được dùng để yêu cầu một phần representation khi tải xuống. `ofFileChannel` tạo phần **request body gửi lên server**; nếu upload cần truyền offset hoặc số phần, phải thực hiện theo giao thức mà server hỗ trợ. Nó cũng không tự tạo `multipart/form-data`; nếu server yêu cầu multipart, ứng dụng phải tạo đúng cấu trúc multipart và boundary.

## 7. Vòng đời dữ liệu, retry và tính nhất quán

`ofFileChannel` và publisher trả về không thay đổi `channel.position()` và không đóng channel. Vì thế, có thể tạo publisher cho nhiều vùng độc lập từ cùng channel mà không cần thay đổi vị trí đọc chung trước mỗi lần gửi.

HTTP Client sử dụng mô hình `Flow.Publisher` cho request body. Trong một số trường hợp request cần được gửi lại, HTTP Client có thể subscribe publisher lần nữa và publisher được kỳ vọng phát lại cùng dữ liệu. Do đó:

- Giữ tệp nguồn ổn định trong suốt quá trình upload và trong khoảng thời gian request có thể được gửi lại.
- Không sửa nội dung, thay thế, truncate hoặc ghi đè tệp khi các publisher còn có thể đọc.
- Với upload song song, ưu tiên các vùng không chồng lấn và giữ nguyên kích thước, nội dung tệp cho tới khi mọi request hoàn tất.
- Nếu cần đảm bảo dữ liệu không đổi, tạo snapshot tệp hoặc dùng cơ chế khóa/quản lý phiên bản phù hợp với ứng dụng.
- Chỉ retry khi endpoint có thể nhận diện phần upload và xử lý gửi lặp an toàn. Cùng một part ID nên đại diện cho cùng một vùng byte và cùng nội dung.

Nếu server trả lỗi sau khi đã nhận một phần body, client không thể tự biết server đã lưu được bao nhiêu dữ liệu ở tầng ứng dụng. Hãy dùng response, trạng thái upload phía server và checksum/part metadata theo giao thức để xác định bước tiếp theo. Không chỉ dựa vào việc `send` ném exception để kết luận server chưa nhận byte nào.

## 8. Hiệu năng và lựa chọn kích thước phần

`ofFileChannel` giúp tránh phải tự nạp toàn bộ tệp hoặc vùng dữ liệu vào một mảng `byte[]`. Nó không loại bỏ chi phí đọc đĩa, TLS, truyền mạng, xử lý ở server hoặc xác minh dữ liệu.

Khi chia tệp thành nhiều phần, cân nhắc:

- **Kích thước phần:** phần nhỏ làm tăng số request và overhead; phần quá lớn làm tăng thời gian gửi lại khi lỗi. Đo với kích thước thực tế thay vì chọn một con số cố định cho mọi hệ thống.
- **Số request đồng thời:** tăng concurrency có thể tăng throughput tới một giới hạn, sau đó gây nghẽn băng thông, CPU, disk I/O, connection pool hoặc giới hạn rate của server.
- **Bộ nhớ:** `ofFileChannel` tránh việc ứng dụng phải giữ một mảng byte lớn cho từng phần; vẫn cần tính đến bộ đệm và tài nguyên của các request đang chạy.
- **Độ ổn định nguồn:** không thay đổi tệp trong lúc đọc song song; mỗi phần phải phản ánh cùng một phiên bản của tệp.
- **Khả năng tiếp tục:** lưu trạng thái các phần server đã xác nhận để chỉ gửi lại phần thiếu, nếu giao thức hỗ trợ.
- **Tính toàn vẹn:** xác minh tổng kích thước và checksum cuối cùng sau khi server ghép xong.

Đo throughput, latency, tỷ lệ lỗi, số lần retry, CPU, bộ nhớ và I/O đĩa. So sánh `ofFileChannel` với `ofFile` hoặc giải pháp hiện tại trong cùng điều kiện mạng, kích thước tệp và server. Không kết luận nhanh hơn chỉ từ việc API có tên `FileChannel`.

## 9. Tương thích JDK và lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không biên dịch được `ofFileChannel` | Đang dùng JDK hoặc API target trước Java 26. | Biên dịch bằng JDK 26+; nếu dùng compiler mới, chọn `--release 26` khi target Java 26. |
| `IndexOutOfBoundsException` | `offset` hoặc `length` âm, hoặc vùng yêu cầu vượt kích thước tệp. | Lấy `channel.size()` và kiểm tra vùng trước khi tạo publisher. |
| `IOException` khi tạo publisher | Channel đã đóng hoặc không xác định được kích thước tệp. | Kiểm tra vòng đời channel và quyền truy cập tệp. |
| Request lỗi khi dùng `sendAsync` | Channel bị đóng trước khi publisher gửi xong. | Đóng channel sau khi future hoàn tất. |
| Server nhận sai phần | Tính offset/length sai hoặc metadata phần không khớp với body. | Dùng khoảng nửa mở `[offset, offset + length)` và kiểm tra part ID/offset theo giao thức. |
| Upload nhiều phần bị thiếu hoặc trùng dữ liệu | Các vùng bị chồng lấn, bỏ sót hoặc ghép sai thứ tự. | Kiểm tra sơ đồ byte ranges và xác nhận trạng thái từng phần. |
| Retry tạo tệp ghép không nhất quán | Tệp nguồn thay đổi giữa các lần subscribe hoặc lần gửi lại. | Dùng snapshot bất biến và mã phần ổn định. |
| Dùng bộ nhớ quá nhiều khi upload tệp lớn | Tự đọc tệp thành `byte[]` hoặc chạy quá nhiều request đồng thời. | Dùng `ofFileChannel`, giới hạn concurrency và đo tài nguyên. |

Mã nguồn dùng API Java 26 có thể biên dịch bằng:

```bash
javac --release 26 -d out src/UploadFileRegion.java
java -cp out UploadFileRegion
```

Không thêm `--enable-preview`; `ofFileChannel` là API đã final trong Java 26. Nếu sản phẩm cần chạy trên Java 25 trở xuống, phải chọn giải pháp tương thích với API của runtime mục tiêu hoặc tách phần triển khai theo phiên bản; không thể gọi trực tiếp phương thức mới này từ mã được biên dịch với API Java 25.

Với ứng dụng dùng Java Platform Module System, module khai báo phụ thuộc vào `java.net.http`:

```java
module com.example.upload {
    requires java.net.http;
}
```

## 10. Checklist trước khi triển khai

- [ ] Đã xác nhận runtime và compile target là Java 26 trở lên.
- [ ] Đã mở tệp bằng `FileChannel` với quyền đọc phù hợp.
- [ ] Đã tính `offset` và `length` theo byte, từ đầu tệp.
- [ ] Đã kiểm tra vùng `[offset, offset + length)` không vượt kích thước tệp.
- [ ] Đã chọn `PUT`/`POST`, endpoint, part ID và metadata theo giao thức upload của server.
- [ ] Đã hiểu `ofFileChannel` không tự thêm header, chia request, ghép phần hoặc retry/resume.
- [ ] Đã giữ channel mở đến khi `send` hoặc toàn bộ future của `sendAsync` hoàn tất.
- [ ] Đã bảo đảm tệp nguồn không bị sửa trong lúc publisher còn có thể đọc.
- [ ] Nếu gửi song song, đã dùng publisher riêng cho từng vùng và các range không chồng lấn.
- [ ] Đã kiểm tra status từng phần, checksum, tổng kích thước và kết quả ghép ở server.
- [ ] Đã đo concurrency, throughput, latency, memory và disk I/O trên workload đại diện.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 26 — `HttpRequest.BodyPublisher`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java SE 26 — `FileChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java SE 27 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 27 — `HttpRequest.BodyPublisher`](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [HTTP Client Updates in Java 26 — Inside.java](https://inside.java/2026/03/04/jdk-26-http-client/)
- [OpenJDK source — `HttpRequest.java`](https://github.com/openjdk/jdk/blob/master/src/java.net.http/share/classes/java/net/http/HttpRequest.java)

*Cập nhật nội dung: 27-11-2026. `ofFileChannel` là API Java SE từ Java 26; kiểm tra Javadoc của JDK mục tiêu và hợp đồng upload của server trước khi áp dụng.*
