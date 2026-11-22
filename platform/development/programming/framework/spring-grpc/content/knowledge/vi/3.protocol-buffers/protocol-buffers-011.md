# Bytes, string và encoding

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **string** dành cho văn bản UTF-8 với **bytes** dành cho dữ liệu nhị phân tùy ý trong proto3.
- Giải thích cách hai kiểu cùng dùng wire type **LEN** nhưng có quy tắc nội dung khác nhau.
- Chuyển đổi giữa Java **String**, **byte[]** và **ByteString** mà không phụ thuộc charset mặc định của máy.
- Hiểu cách ProtoJSON biểu diễn string và bytes.
- Chọn kiểu field phù hợp cho nội dung văn bản, tệp, hash, token và payload nhị phân trong dịch vụ Spring gRPC.
- Đánh giá rủi ro khi thay đổi field từ string sang bytes hoặc ngược lại.

## 1. Chọn string hay bytes?

Trong hợp đồng **SPRING_GRPC**, Protocol Buffers định nghĩa dữ liệu được truyền giữa client và server. Hai kiểu **string** và **bytes** đều chứa một dãy byte trên đường truyền, nhưng chúng mang ngữ nghĩa khác nhau:

- **string** dành cho văn bản được mã hóa UTF-8 hợp lệ. Người đọc có thể hiểu nội dung như văn bản Unicode.
- **bytes** dành cho một chuỗi byte tùy ý. Nội dung không bắt buộc là văn bản và có thể chứa mọi giá trị byte từ 0 đến 255.

Ví dụ:

~~~proto
syntax = "proto3";

message Document {
  string title = 1;
  string description = 2;
  bytes content = 3;
  bytes sha256_digest = 4;
}
~~~

**title** và **description** là văn bản. **content** có thể là dữ liệu PDF, ảnh, tệp nén hoặc payload mã hóa. **sha256_digest** là 32 byte kết quả băm, không phải chuỗi ký tự tùy ý.

| Dữ liệu | Kiểu nên dùng | Lý do |
| --- | --- | --- |
| Tên, mô tả, địa chỉ email | **string** | Là văn bản UTF-8. |
| Nội dung văn bản thuần | **string** | Cần xử lý như chuỗi Unicode. |
| Ảnh, PDF, dữ liệu nén | **bytes** | Có thể chứa byte không hợp lệ với UTF-8. |
| Hash, chữ ký số, khóa nhị phân | **bytes** | Cần giữ nguyên từng byte. |
| Token dạng văn bản theo hợp đồng | **string** | Nếu token được định nghĩa là chuỗi ký tự. |
| Token nhị phân hoặc ciphertext | **bytes** | Không được diễn giải như văn bản. |

Đừng chọn **bytes** chỉ vì Protobuf cuối cùng cũng truyền byte. Chọn kiểu dựa trên ý nghĩa dữ liệu và cách client/server phải xử lý nó.

## 2. string trong proto3 là văn bản UTF-8

Khai báo:

~~~proto
message Greeting {
  string message = 1;
}
~~~

Field **string** phải chứa chuỗi UTF-8 hợp lệ. Protobuf không lưu chuỗi theo charset mặc định của hệ điều hành; định dạng wire sử dụng UTF-8. Khi parser gặp nội dung string không hợp lệ UTF-8, message không được xem là một string Protobuf hợp lệ và quá trình parse có thể thất bại.

Ví dụ văn bản tiếng Việt:

~~~java
String message = "Xin chào";
Greeting greeting = Greeting.newBuilder()
    .setMessage(message)
    .build();
~~~

Java biểu diễn **String** theo UTF-16 nội bộ, còn Protobuf chuyển nội dung string sang UTF-8 khi serialize. Người viết ứng dụng không cần tự chuyển sang byte[] trước khi gọi setter của field string.

Một điểm quan trọng là **số ký tự không bằng số byte UTF-8**. Ví dụ, chữ ASCII thường dùng một byte; nhiều ký tự tiếng Việt có dấu cần nhiều byte. Không dùng **String.length()** để dự đoán kích thước payload trên wire.

~~~java
import java.nio.charset.StandardCharsets;

String text = "Xin chào";
int utf8Length = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println(text.length()); // Số đơn vị mã UTF-16 của Java String
System.out.println(utf8Length);    // Số byte khi mã hóa UTF-8
~~~

Nếu nghiệp vụ coi hai cách viết Unicode có dấu là tương đương, chẳng hạn ký tự dựng sẵn và ký tự ghép từ dấu kết hợp, ứng dụng cần quy định chuẩn hóa Unicode ở tầng nghiệp vụ. Protobuf bảo toàn chuỗi đã nhận; nó không tự chuẩn hóa nội dung thành một dạng Unicode canonical.

## 3. bytes biểu diễn dữ liệu nhị phân tùy ý

Khai báo:

~~~proto
message UploadChunk {
  string file_name = 1;
  bytes data = 2;
}
~~~

Field **data** không có yêu cầu UTF-8. Nó có thể chứa byte 0x00, 0xFF, byte điều khiển hoặc bất kỳ mẫu byte nào:

~~~java
import com.google.protobuf.ByteString;

byte[] raw = new byte[] {
    0x00, 0x41, (byte) 0xFF, 0x0A
};

UploadChunk chunk = UploadChunk.newBuilder()
    .setFileName("sample.bin")
    .setData(ByteString.copyFrom(raw))
    .build();
~~~

Java Protobuf ánh xạ:

| Kiểu proto3 | Kiểu Java |
| --- | --- |
| **string** | **java.lang.String** |
| **bytes** | **com.google.protobuf.ByteString** |

**ByteString** là kiểu byte bất biến (immutable) của Protobuf. Builder dùng nó để giữ dữ liệu nhị phân; message đã build không cho phép sửa nội dung ByteString tại chỗ. Có thể lấy bản sao byte[] bằng **toByteArray()** khi một API khác cần mảng byte.

Không chuyển dữ liệu nhị phân tùy ý thành String bằng charset mặc định. Việc giải mã có thể thay byte không hợp lệ bằng ký tự thay thế, làm thay đổi nội dung và khiến hash/chữ ký không còn đúng.

## 4. Java API: chuyển đổi String, byte[] và ByteString

### Tạo ByteString từ văn bản UTF-8

Khi một field bytes được quy ước chứa văn bản UTF-8, có thể dùng:

~~~java
import com.google.protobuf.ByteString;

String note = "Xin chào";
ByteString encodedText = ByteString.copyFromUtf8(note);
~~~

Phương thức **copyFromUtf8()** mã hóa String thành byte UTF-8 rồi tạo ByteString. Đây là cách thuận tiện khi hợp đồng bytes thực sự quy định payload là UTF-8.

### Đọc ByteString thành văn bản

Chỉ chuyển bytes thành String sau khi biết hợp đồng quy định nội dung là UTF-8. Nếu dữ liệu có thể đến từ nguồn không tin cậy, kiểm tra tính hợp lệ trước:

~~~java
ByteString payload = chunk.getData();

if (payload.isValidUtf8()) {
    String text = payload.toStringUtf8();
    processText(text);
} else {
    rejectInvalidTextPayload();
}
~~~

**toStringUtf8()** không biến dữ liệu nhị phân thành văn bản có ý nghĩa. Với byte sequence không hợp lệ, việc giải mã có thể thay thế đoạn lỗi; vì vậy phải xác nhận hợp đồng hoặc kiểm tra UTF-8 trước khi xử lý.

### Dùng byte[] với charset tường minh

Khi cần tương tác với API Java nhận byte[], luôn chỉ rõ UTF-8:

~~~java
import java.nio.charset.StandardCharsets;

String text = "Spring gRPC";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

String restored = new String(utf8, StandardCharsets.UTF_8);
~~~

Không dùng **new String(bytes)** hoặc **text.getBytes()** không chỉ định charset trong code xử lý giao thức. Kết quả có thể khác giữa máy phát triển, container và môi trường production.

### ByteString và thao tác byte

Các phương thức hữu ích:

| Phương thức | Công dụng |
| --- | --- |
| **ByteString.copyFrom(byte[])** | Tạo ByteString từ byte array. |
| **ByteString.copyFromUtf8(String)** | Mã hóa String thành UTF-8 rồi tạo ByteString. |
| **byteString.toByteArray()** | Lấy byte array. |
| **byteString.toStringUtf8()** | Giải mã byte thành String UTF-8. |
| **byteString.isValidUtf8()** | Kiểm tra nội dung có phải UTF-8 hợp lệ. |
| **byteString.size()** | Số byte. |
| **byteString.isEmpty()** | Kiểm tra không có byte nào. |

ByteString bất biến giúp tránh việc một mảng byte bên ngoài bị thay đổi sau khi message được dựng. Với payload lớn, vẫn cần cân nhắc sao chép bộ nhớ và giới hạn kích thước message.

## 5. string và bytes có cùng wire type nhưng không cùng ngữ nghĩa

Trong Protobuf binary, **string** và **bytes** đều dùng wire type **2 (LEN, length-delimited)**. Cấu trúc gồm:

1. Tag chứa field number và wire type.
2. Độ dài payload được mã hóa bằng varint.
3. Các byte nội dung.

Ví dụ:

~~~proto
message Sample {
  string text = 1;
  bytes raw = 2;
}
~~~

Với **text = "A"** và **raw = [0x00, 0xFF]**, phần payload có thể là:

~~~text
0A 01 41
|  |  +-- Byte UTF-8 của ký tự A
|  +----- Độ dài: 1
+-------- Tag field 1, wire type 2

12 02 00 FF
|  |  |  |
|  |  +--+-- Hai byte dữ liệu tùy ý
|  +-------- Độ dài: 2
+----------- Tag field 2, wire type 2
~~~

Wire type giống nhau không có nghĩa hai kiểu thay thế an toàn cho nhau. Parser string phải kiểm tra UTF-8; parser bytes chấp nhận byte tùy ý. API Java và ProtoJSON cũng khác nhau.

## 6. ProtoJSON biểu diễn string và bytes

ProtoJSON dùng:

- **string**: JSON string, có escape theo quy tắc JSON.
- **bytes**: chuỗi Base64 biểu diễn byte sequence.

Với:

~~~proto
message Attachment {
  string file_name = 1;
  string description = 2;
  bytes content = 3;
}
~~~

Một biểu diễn JSON:

~~~json
{
  "fileName": "report.pdf",
  "description": "Báo cáo tháng 11",
  "content": "JVBERi0xLjQK"
}
~~~

**content** là Base64, không phải văn bản PDF đã giải mã. Client JSON phải Base64-decode để khôi phục đúng byte ban đầu. Khi dùng **JsonFormat** của **protobuf-java-util**, thư viện xử lý quy tắc này:

~~~java
import com.google.protobuf.ByteString;
import com.google.protobuf.util.JsonFormat;

Attachment attachment = Attachment.newBuilder()
    .setFileName("report.pdf")
    .setContent(ByteString.copyFrom(new byte[] {
        0x01, 0x02, (byte) 0xFE
    }))
    .build();

String json = JsonFormat.printer().print(attachment);

Attachment.Builder parsed = Attachment.newBuilder();
JsonFormat.parser().merge(json, parsed);

System.out.println(
    parsed.build().getContent().equals(attachment.getContent()));
// true
~~~

Đừng dùng serializer JSON tổng quát rồi mặc định rằng nó tuân theo ProtoJSON. Đặc biệt, bytes phải được biểu diễn bằng Base64 theo hợp đồng Protobuf; cách một thư viện khác serialize ByteString có thể không tương thích.

## 7. Đổi field từ string sang bytes có an toàn không?

Về wire format, string và bytes đều length-delimited. Nếu payload string là UTF-8 hợp lệ, byte sequence có thể được đọc như bytes mà không đổi nội dung nhị phân. Tuy nhiên, thay kiểu field đã phát hành vẫn có tác động lớn:

| Khía cạnh | Khi đổi string thành bytes |
| --- | --- |
| Field number và wire type | Có thể giữ nguyên nếu không đổi số; cả hai dùng wire type 2. |
| Binary payload | Các byte UTF-8 cũ có thể được đọc như bytes. |
| Dữ liệu cũ không phải UTF-8 | Không thể tồn tại hợp lệ như string Protobuf; nếu có ở nguồn khác, parser string có thể đã từ chối. |
| API Java | Getter đổi từ **String** sang **ByteString**; code gọi phải sửa. |
| ProtoJSON | Giá trị đổi từ JSON string sang chuỗi Base64. |
| Ý nghĩa nghiệp vụ | Client có thể ngừng hiểu nội dung như văn bản. |

Chiều ngược lại, đổi bytes thành string chỉ có thể xử lý an toàn khi **mọi payload hiện có đều là UTF-8 hợp lệ** và tất cả client chấp nhận thay đổi API/JSON. Byte tùy ý như ảnh, ciphertext hoặc hash không thể chuyển thành string một cách trung thực.

Vì vậy, không coi việc cùng wire type là lý do đủ để đổi kiểu. Nếu ý nghĩa dữ liệu thay đổi, cách an toàn thường là thêm field mới với số chưa dùng, triển khai giai đoạn chuyển tiếp, rồi ngừng field cũ và reserve số/tên đã bỏ.

## 8. Chọn encoding cho dữ liệu văn bản trong bytes

Đôi khi hệ thống nhận một payload bytes nhưng nội dung thực chất là văn bản. Khi đó, encoding phải là một phần của hợp đồng:

~~~proto
message TextPayload {
  string media_type = 1;
  string charset = 2;
  bytes content = 3;
}
~~~

Nếu quy định **charset = "UTF-8"**, consumer có thể giải mã content theo UTF-8. Nếu hỗ trợ nhiều charset, phải có danh sách được cho phép, cách xử lý charset không hỗ trợ và quy tắc chuyển đổi rõ ràng.

Không đoán encoding từ byte đầu tiên hoặc từ môi trường chạy. Dùng một quy ước cố định khi có thể; UTF-8 thường là lựa chọn phù hợp cho văn bản mới.

Nếu payload là dữ liệu văn bản thông thường và không cần giữ nguyên dạng byte gốc, dùng **string** đơn giản hơn. Dùng bytes kèm charset khi hợp đồng cần lưu chính xác byte gốc, hỗ trợ nhiều định dạng hoặc truyền một nội dung chưa giải mã.

## 9. Payload lớn và streaming gRPC

Field bytes phù hợp với dữ liệu nhị phân nhỏ hoặc vừa nằm trong một message. Tuy nhiên, nhúng toàn bộ tệp lớn vào một request có thể:

- Tăng bộ nhớ cần thiết ở cả client và server.
- Tạo bản sao byte array khi chuyển đổi giữa API.
- Làm tăng độ trễ trước khi server có thể xử lý dữ liệu.
- Chạm giới hạn kích thước message hoặc giới hạn do server/client cấu hình.

Với tệp lớn, cân nhắc **client-streaming RPC** gửi nhiều chunk:

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 offset = 2;
  bytes data = 3;
  bool last = 4;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Mỗi message mang một phần dữ liệu; server kiểm tra upload id, offset, thứ tự chunk, kích thước và điều kiện kết thúc. Ví dụ chỉ minh họa cấu trúc schema; ứng dụng còn phải định nghĩa xử lý chunk lặp, chunk thiếu, retry, xác thực và lưu trữ tạm.

Không chia payload thành chunk tùy tiện mà bỏ qua giới hạn message, luồng điều khiển và khả năng khôi phục. Với tệp rất lớn, streaming giúp xử lý tuần tự và kiểm soát bộ nhớ tốt hơn so với một message đơn khổng lồ.

## 10. Kiểm thử encoding và round-trip

Một bộ kiểm thử nên bao gồm:

1. String ASCII và Unicode, bao gồm văn bản có dấu.
2. Bytes có byte 0x00, 0xFF và các byte không phải UTF-8.
3. Serialize/parse Protobuf binary và so sánh đúng nội dung.
4. Chuyển ProtoJSON, xác nhận bytes được xuất Base64 và parse lại không đổi byte.
5. Từ chối hoặc xử lý có chủ đích khi bytes được yêu cầu giải mã thành UTF-8 nhưng dữ liệu không hợp lệ.
6. Kiểm tra kích thước payload và hành vi chunk nếu dùng streaming.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.content.v1.Sample;
import com.google.protobuf.ByteString;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class StringBytesTest {
    @Test
    void preservesUnicodeStringAndArbitraryBytes() throws Exception {
        byte[] raw = new byte[] {
            0x00, 0x41, (byte) 0xFF
        };

        Sample source = Sample.newBuilder()
            .setText("Xin chào")
            .setRaw(ByteString.copyFrom(raw))
            .build();

        Sample decoded = Sample.parseFrom(source.toByteArray());

        assertEquals("Xin chào", decoded.getText());
        assertArrayEquals(raw, decoded.getRaw().toByteArray());
    }

    @Test
    void preservesBytesThroughProtoJson() throws Exception {
        Sample source = Sample.newBuilder()
            .setRaw(ByteString.copyFrom(new byte[] {
                0x00, (byte) 0xFF
            }))
            .build();

        String json = JsonFormat.printer().print(source);
        Sample.Builder builder = Sample.newBuilder();
        JsonFormat.parser().merge(json, builder);

        assertEquals(source.getRaw(), builder.build().getRaw());
    }

    @Test
    void validatesUtf8BeforeTreatingBytesAsText() {
        ByteString arbitrary = ByteString.copyFrom(
            new byte[] { (byte) 0xFF, 0x00 });

        assertFalse(arbitrary.isValidUtf8());
    }
}
~~~

Các đoạn trên dùng lớp **Sample** với schema:

~~~proto
syntax = "proto3";

package learning.content.v1;
option java_package = "com.example.content.v1";
option java_multiple_files = true;

message Sample {
  string text = 1;
  bytes raw = 2;
}
~~~

Đây là ví dụ kiểm thử theo API Java được sinh; cần chạy trong dự án với phiên bản Protobuf và protobuf-java-util tương thích.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng string cho ảnh hoặc ciphertext | Parser/serializer văn bản có thể từ chối hoặc làm hỏng byte | Dùng **bytes**. |
| Dùng bytes cho văn bản mà không ghi encoding | Consumer không biết cách giải mã | Dùng **string** hoặc quy định charset rõ ràng. |
| Gọi getBytes() không chỉ định charset | Kết quả khác giữa môi trường | Dùng **StandardCharsets.UTF_8**. |
| Chuyển bytes tùy ý sang String | Mất hoặc thay byte không hợp lệ | Kiểm tra UTF-8 và chỉ giải mã theo hợp đồng. |
| Nghĩ string và bytes thay thế an toàn vì cùng wire type | Phá API Java và ProtoJSON, có thể sai ngữ nghĩa | Đánh giá binary, source, JSON và nghiệp vụ riêng. |
| Tự serialize ByteString bằng JSON tổng quát | JSON không đúng ProtoJSON | Dùng **JsonFormat** khi cần ProtoJSON. |
| Gửi tệp lớn trong một message đơn | Tốn bộ nhớ, độ trễ và có thể vượt giới hạn | Cân nhắc client-streaming với chunk có kiểm soát. |

## 12. Bài tập thực hành

Thiết kế message cho dịch vụ lưu tài liệu:

~~~proto
message StoredDocument {
  string document_id = 1;
  string file_name = 2;
  string media_type = 3;
  bytes content = 4;
  bytes sha256_digest = 5;
}
~~~

Hãy:

1. Giải thích vì sao **file_name** và **media_type** là string, còn **content** và **sha256_digest** là bytes.
2. Tạo message Java chứa nội dung có byte 0x00 và 0xFF; serialize/parse rồi xác nhận mọi byte được giữ nguyên.
3. Chuyển message sang ProtoJSON, xác định field bytes được biểu diễn như thế nào.
4. Thử giải mã content thành UTF-8 và kiểm tra **isValidUtf8()** trước khi xử lý.
5. Giải thích rủi ro khi đổi field content từ bytes sang string mà giữ nguyên số hiệu.
6. Đề xuất RPC streaming nếu tài liệu có thể lớn hơn giới hạn message mà hệ thống chấp nhận.

**Tiêu chí hoàn thành:** chọn đúng kiểu theo ngữ nghĩa, chuyển đổi Java không phụ thuộc charset mặc định, giữ nguyên byte qua round-trip và giải thích được sự khác nhau giữa wire compatibility với tương thích API/JSON.

## 13. Ghi nhớ

- **string** là văn bản UTF-8 hợp lệ; **bytes** là dữ liệu nhị phân tùy ý.
- Java ánh xạ string thành **String**, bytes thành **ByteString**.
- Cả hai dùng wire type **LEN**, nhưng quy tắc kiểm tra nội dung và API Java khác nhau.
- ProtoJSON xuất string thành JSON string và bytes thành Base64.
- Chỉ chuyển bytes thành văn bản khi biết encoding; dùng UTF-8 tường minh và kiểm tra dữ liệu khi cần.
- Cùng wire type không bảo đảm thay đổi string/bytes tương thích với mã Java, JSON hoặc nghiệp vụ.
- Với payload lớn, cân nhắc streaming thay vì gom toàn bộ dữ liệu vào một message.

Chọn đúng string và bytes giúp hợp đồng Protocol Buffers bảo toàn nội dung, tránh lỗi encoding giữa các môi trường và hỗ trợ dịch vụ Spring gRPC trao đổi cả văn bản lẫn dữ liệu nhị phân một cách tin cậy.
