# Scalar types và kiểu dữ liệu tương ứng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện đầy đủ **15 kiểu scalar** của Protocol Buffers **proto3** và kiểu Java tương ứng sau khi sinh mã.
- Chọn kiểu số có dấu, không dấu, ZigZag hoặc kích thước cố định dựa trên miền giá trị và cách mã hóa.
- Xử lý đúng **uint32/uint64** trong Java, tránh nhầm lẫn giữa bit biểu diễn với giá trị số không dấu.
- Phân biệt **string** (văn bản UTF-8) với **bytes** (dữ liệu nhị phân), cũng như rủi ro sai số của **float/double**.
- Hiểu giá trị mặc định, **field presence**, dạng JSON của Protobuf và cách kiểm tra dữ liệu ở biên client/server Spring gRPC.

## 1. Vì sao chọn kiểu scalar quan trọng trong Spring gRPC?

Khi phát triển dịch vụ **SPRING_GRPC**, hợp đồng **.proto** xác định loại dữ liệu client gửi và server nhận. Protobuf sinh các lớp Java với kiểu dữ liệu và API tương ứng; gRPC truyền các message đó ở dạng nhị phân trong RPC unary hoặc streaming. Chọn kiểu field vì thế tác động trực tiếp đến **miền giá trị hợp lệ**, **kích thước dữ liệu truyền**, **cách lập trình viên Java đọc giá trị** và **khả năng tương thích giữa các phiên bản**.

**Scalar** là kiểu giá trị đơn lẻ có sẵn trong ngôn ngữ schema, ví dụ một số nguyên, số thực, cờ đúng/sai, chuỗi hoặc dãy byte. Scalar khác với **message** (cấu trúc có các field), **enum** (tập giá trị đặt tên) và các tổ hợp như **repeated**, **map**, **oneof**. Một field scalar có dạng:

~~~proto
int32 retry_count = 1;
string device_id = 2;
bool active = 3;
~~~

Mỗi dòng gồm **kiểu**, **tên field** và **số hiệu field**. Số hiệu, không phải tên, được dùng để nhận diện field trong bản mã hóa nhị phân. Thay đổi kiểu của field đã triển khai cần được đánh giá riêng về độ tương thích, kể cả khi phía Java vẫn hiển thị cùng một kiểu nguyên thủy.

## 2. Bảng tra cứu đầy đủ 15 kiểu scalar của proto3

Bảng này mô tả API Java phổ biến do **protoc** sinh ra khi dùng **protobuf-java**:

| Kiểu .proto | Kiểu getter/setter Java | Giá trị mặc định | Kiểu mã hóa trên wire |
| --- | --- | --- | --- |
| **double** | **double** | **0.0d** | 64-bit cố định |
| **float** | **float** | **0.0f** | 32-bit cố định |
| **int32** | **int** | **0** | Varint |
| **int64** | **long** | **0L** | Varint |
| **uint32** | **int** | **0** | Varint, xem như không dấu |
| **uint64** | **long** | **0L** | Varint, xem như không dấu |
| **sint32** | **int** | **0** | Varint + ZigZag |
| **sint64** | **long** | **0L** | Varint + ZigZag |
| **fixed32** | **int** | **0** | 32-bit cố định, không dấu |
| **fixed64** | **long** | **0L** | 64-bit cố định, không dấu |
| **sfixed32** | **int** | **0** | 32-bit cố định, có dấu |
| **sfixed64** | **long** | **0L** | 64-bit cố định, có dấu |
| **bool** | **boolean** | **false** | Varint |
| **string** | **String** | **""** | Có độ dài, UTF-8 |
| **bytes** | **com.google.protobuf.ByteString** | **ByteString.EMPTY** | Có độ dài, byte thô |

**Điểm cần nhớ:** có nhiều kiểu .proto cùng ánh xạ sang **int** hoặc **long** của Java nhưng chúng **không tương đương về miền giá trị hoặc cách mã hóa**. Ví dụ **int32**, **sint32**, **uint32**, **fixed32** và **sfixed32** đều có API Java dựa trên **int**, nhưng payload nhị phân và cách diễn giải không giống nhau.

**Enum** có giá trị số ở mức wire nhưng là loại schema riêng, không thuộc danh sách 15 scalar nguyên thủy. Enum proto3 thường có giá trị đầu tiên bằng 0; lớp Java sinh một kiểu enum thay vì dùng **int** làm API chính.

## 3. Miền giá trị: signed, unsigned và số thực

### 3.1. Số nguyên 32-bit và 64-bit

| Nhóm kiểu | Miền giá trị toán học |
| --- | --- |
| **int32**, **sint32**, **sfixed32** | −2.147.483.648 đến 2.147.483.647 |
| **uint32**, **fixed32** | 0 đến 4.294.967.295 |
| **int64**, **sint64**, **sfixed64** | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| **uint64**, **fixed64** | 0 đến 18.446.744.073.709.551.615 |

Java **int** và **long** là kiểu có dấu. Protobuf vẫn mã hóa được trọn miền **uint32/uint64**, nhưng khi đọc qua Java, bit cao nhất có thể khiến giá trị được hiển thị thành số âm. Đây **không phải dữ liệu hỏng**; phải dùng API không dấu để diễn giải:

~~~java
// uint32 tối đa là 4_294_967_295, vượt Integer.MAX_VALUE.
int unsigned32 = Integer.parseUnsignedInt("4294967295");
System.out.println(unsigned32);                    // -1 (cách nhìn có dấu)
System.out.println(Integer.toUnsignedString(unsigned32)); // 4294967295

// uint64 tối đa là 18_446_744_073_709_551_615.
long unsigned64 =
    Long.parseUnsignedLong("18446744073709551615");
System.out.println(unsigned64);                    // -1 (cách nhìn có dấu)
System.out.println(Long.toUnsignedString(unsigned64)); // 18446744073709551615
~~~

Khi so sánh **uint32/uint64**, dùng **Integer.compareUnsigned(...)** hoặc **Long.compareUnsigned(...)**; khi chia, dùng **divideUnsigned(...)** nếu cần. Đừng dùng phép so sánh có dấu thông thường để so thứ tự của các giá trị ở nửa trên miền không dấu. Nếu cần tính toán với số nguyên không dấu 64-bit vượt khả năng biểu diễn số dương của **long**, có thể chuyển sang **BigInteger**:

~~~java
import java.math.BigInteger;

long raw = Long.parseUnsignedLong("18446744073709551615");
BigInteger value = new BigInteger(Long.toUnsignedString(raw));
System.out.println(value.add(BigInteger.ONE)); // 18446744073709551616
~~~

Không truyền trực tiếp literal **4294967295** vào setter kiểu **int** hoặc literal **18446744073709551615** vào setter kiểu **long**; các literal ấy vượt phạm vi Java tương ứng. **parseUnsignedInt/parseUnsignedLong** là cách tiện lợi khi nhận dữ liệu đầu vào dạng thập phân.

### 3.2. float và double

**float** sử dụng định dạng IEEE 754 binary32 (thường khoảng 6–9 chữ số thập phân có nghĩa); **double** dùng IEEE 754 binary64 (thường khoảng 15–17 chữ số có nghĩa). Cả hai là số thực **xấp xỉ**:

~~~java
float f = 0.1f;
double d = 0.1d;

System.out.println(f == 0.1d); // false: hai kiểu có độ chính xác khác nhau
System.out.println(d + 0.2d == 0.3d); // false: sai số biểu diễn nhị phân
~~~

Khi thiết kế giao thức:

- Dùng **float** cho mẫu đo có thể chấp nhận độ chính xác thấp hơn và cần giảm kích thước payload.
- Dùng **double** khi thuật toán cần độ chính xác cao hơn, nhưng vẫn là số thực xấp xỉ.
- Không dùng **float/double** để biểu diễn chính xác tiền hoặc số thập phân phải bảo toàn từng chữ số. Với tiền, thường dùng **int64 amount_minor_units** (ví dụ số đồng/xu nhỏ nhất) kèm quy ước đơn vị, hoặc một cấu trúc decimal có thang đo rõ ràng.
- **NaN**, **+Infinity**, **−Infinity** có thể tồn tại trong **float/double**; nếu nghiệp vụ chỉ chấp nhận số hữu hạn, phải xác minh ở server bằng **Float.isFinite(...)** hoặc **Double.isFinite(...)**.

Tên field nên cho biết đơn vị: **duration_ms**, **temperature_milli_c**, **distance_meters** rõ nghĩa hơn các tên như **duration**, **value**, **size**.

## 4. Varint, ZigZag và fixed: cùng là số nguyên nhưng mã hóa khác nhau

Protobuf không ghi một field theo cách "tên field + giá trị". Mỗi field có **tag** chứa số hiệu và loại wire, sau đó là giá trị mã hóa. Về khái niệm:

~~~text
Message bytes
  |
  +-- tag(field_number, wire_type) -- encoded value
  +-- tag(field_number, wire_type) -- encoded value
  +-- ...
~~~

Một số **wire type** liên quan đến scalar:

| Wire type | Đại diện | Kiểu dùng |
| --- | --- | --- |
| **0 (Varint)** | Số nguyên mã hóa theo nhóm 7 bit | int32/int64/uint32/uint64/sint32/sint64/bool |
| **1 (64-bit)** | Chính xác 8 byte dữ liệu | fixed64/sfixed64/double |
| **2 (Length-delimited)** | Độ dài rồi đến nội dung | string/bytes; cả repeated scalar dạng packed |
| **5 (32-bit)** | Chính xác 4 byte dữ liệu | fixed32/sfixed32/float |

**Varint** dùng ít byte cho giá trị số không dấu nhỏ, nhiều byte hơn khi số lớn. Với **int32/int64**, các giá trị âm thường mã hóa kém hiệu quả vì cách biểu diễn bù hai: ví dụ **int32 = -1** chiếm **10 byte cho phần giá trị varint**, chưa tính tag.

**sint32/sint64** dùng phép biến đổi **ZigZag** trước khi mã hóa varint, đưa số âm và dương nhỏ về số nguyên không dấu nhỏ:

| Số có dấu gốc | Giá trị sau ZigZag |
| --- | --- |
| 0 | 0 |
| −1 | 1 |
| 1 | 2 |
| −2 | 3 |
| 2 | 4 |

Vì vậy **sint32 = -1** chỉ cần **1 byte cho phần giá trị varint**. Ngược lại, với dữ liệu hầu như không âm, **int32/uint32** có thể thích hợp hơn vì ZigZag còn làm lớn giá trị dương. ZigZag **không thay đổi** kiểu Java: getter của **sint32** vẫn trả **int**, của **sint64** vẫn trả **long**.

**fixed32/sfixed32** luôn dùng **4 byte cho phần giá trị**; **fixed64/sfixed64** luôn dùng **8 byte**, chưa tính tag. Chúng có thể hiệu quả khi giá trị thường lớn, khiến varint phải dùng nhiều byte. Điểm khác biệt giữa **fixed** và **sfixed** nằm ở **cách diễn giải signed/unsigned**, không phải số byte.

Ví dụ cụ thể về một field:

~~~proto
message Counter {
  int32 retry_count = 1;
}
~~~

Nếu **retry_count = 150**, tag field 1/varint là **0x08**, còn giá trị 150 mã hóa thành **0x96 0x01**. Payload của message là **08 96 01** (3 byte). Đây là ví dụ cho thấy kích thước thực tế còn gồm tag, không chỉ byte của giá trị.

### Chọn kiểu số nào?

| Dữ liệu thực tế | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Số lần thử, chỉ số nhỏ không âm | **int32** hoặc **uint32** | Varint gọn cho giá trị nhỏ |
| Sai lệch nhiệt độ, hiệu số âm/dương gần 0 | **sint32** hoặc **sint64** | ZigZag tối ưu cho số âm nhỏ |
| Mã đếm không dấu có thể vượt giới hạn số dương Java | **uint32/uint64** | Đủ miền, nhưng Java phải diễn giải không dấu |
| Giá trị 32-bit rất lớn xuất hiện thường xuyên | **fixed32/sfixed32** | Kích thước cố định có thể nhỏ hơn varint |
| Giá trị 64-bit rất lớn xuất hiện thường xuyên | **fixed64/sfixed64** | 8 byte cố định cho phần giá trị |
| Đo lường liên tục có sai số chấp nhận được | **float/double** | Biểu diễn số thực, không chính xác tuyệt đối |

Không thay đổi kiểu của **một field đã triển khai** chỉ vì thấy lựa chọn khác tiết kiệm byte hơn. **int32** và **sint32** tuy đều thuộc wire type 0 nhưng diễn giải giá trị khác nhau; **float** và **fixed32** tuy đều wire type 5 nhưng ý nghĩa bit khác nhau. Khi cần đổi nghĩa hay mã hóa, cách an toàn thường là **thêm field mới với số hiệu mới**, chuyển dần client/server, rồi **reserve** số hiệu cũ.

## 5. string và bytes: văn bản khác dữ liệu nhị phân

Hai kiểu này cùng dùng **wire type 2** (có độ dài), nhưng khác hẳn ngữ nghĩa:

| Tiêu chí | **string** | **bytes** |
| --- | --- | --- |
| Ý nghĩa | Văn bản Unicode mã hóa UTF-8 | Chuỗi byte bất kỳ |
| Kiểu Java | **String** | **ByteString** bất biến |
| Mặc định | **""** | **ByteString.EMPTY** |
| Dữ liệu phù hợp | Tên, mô tả, mã văn bản, email | Payload nhị phân, dữ liệu đã nén, nội dung mã hóa |
| Protobuf JSON | Chuỗi ký tự JSON | Chuỗi Base64 |

Ví dụ:

~~~proto
message PayloadExample {
  string display_name = 1;
  bytes raw_payload = 2;
}
~~~

~~~java
import com.google.protobuf.ByteString;

byte[] raw = new byte[] {(byte) 0x00, (byte) 0xFF};

PayloadExample sample = PayloadExample.newBuilder()
    .setDisplayName("Thiết bị số 1")
    .setRawPayload(ByteString.copyFrom(raw))
    .build();

String text = sample.getDisplayName();
ByteString payload = sample.getRawPayload();
byte[] copiedBytes = payload.toByteArray();
System.out.println(payload.size()); // 2
~~~

**ByteString.copyFrom(...)** tạo giá trị bất biến từ byte đầu vào. Khi cần xử lý nội dung được biết chắc là UTF-8, có thể dùng **ByteString.copyFromUtf8("...")** và **toStringUtf8()**; đừng tự động giải mã dữ liệu nhị phân bất kỳ thành văn bản.

**string** phải biểu diễn UTF-8 hợp lệ khi truyền qua Protobuf. Không dùng **bytes** để lách yêu cầu kiểm tra encoding cho dữ liệu thực sự là văn bản. Ngược lại, không đưa dữ liệu ảnh nén hoặc gói nhị phân vào **string** chỉ vì Java có thể tạo một chuỗi ký tự từ byte.

**bytes** và **string** có thể chứa dữ liệu lớn; Protobuf không tự áp đặt giới hạn nghiệp vụ như kích thước ảnh tối đa. Ở ứng dụng Spring gRPC, cần kết hợp kiểm tra kích thước payload, cấu hình giới hạn message gRPC và chính sách lưu trữ phù hợp. Tránh đặt dữ liệu nhị phân khổng lồ vào một request unary nếu luồng truyền/chia khối phù hợp hơn.

## 6. Giá trị mặc định và field presence của scalar

Với **scalar thông thường** của proto3, nếu bên gửi không đặt field, Java vẫn trả về giá trị mặc định. Ví dụ:

~~~proto
message PatchDeviceRequest {
  string device_id = 1;
  bool enabled = 2;
  int32 threshold = 3;
  optional bool calibrated = 4;
  optional int32 calibration_offset = 5;
}
~~~

Trạng thái khi tạo message chỉ có **device_id**:

| Field | Giá trị getter | Có phương thức has...? | Ý nghĩa |
| --- | --- | --- | --- |
| **enabled** | **false** | Không | Không phân biệt "không gửi" với "gửi false" |
| **threshold** | **0** | Không | Không phân biệt "không gửi" với "gửi 0" |
| **calibrated** | **false** | **hasCalibrated()** | Phân biệt vắng mặt với chủ đích đặt false |
| **calibration_offset** | **0** | **hasCalibrationOffset()** | Phân biệt vắng mặt với chủ đích đặt 0 |

Với **optional**, explicit presence được ghi nhớ trong builder/message, ngay cả khi giá trị đúng bằng mặc định:

~~~java
PatchDeviceRequest notSet = PatchDeviceRequest.newBuilder()
    .setDeviceId("sensor-7")
    .build();

PatchDeviceRequest explicitlyFalse = PatchDeviceRequest.newBuilder()
    .setDeviceId("sensor-7")
    .setCalibrated(false)
    .setCalibrationOffset(0)
    .build();

System.out.println(notSet.getCalibrated());       // false
System.out.println(notSet.hasCalibrated());       // false
System.out.println(explicitlyFalse.getCalibrated()); // false
System.out.println(explicitlyFalse.hasCalibrated()); // true
System.out.println(explicitlyFalse.hasCalibrationOffset()); // true
~~~

Scalar không có presence thường **không được tuần tự hóa khi bằng giá trị mặc định**. Scalar **optional** có presence sẽ mang thông tin "đã đặt" khi được serialize, kể cả giá trị bằng mặc định. Đây là khác biệt quan trọng đối với API cập nhật một phần hoặc lệnh "đặt lại giá trị".

**Proto3 không có nhãn required**: ứng dụng phải tự kiểm tra field bắt buộc theo nghiệp vụ, chẳng hạn **device_id** không được để trống. Getter của scalar không có presence không trả **null**; setter của mã Java Protobuf sinh cũng không dùng **null** như cách báo "vắng mặt".

**repeated** các giá trị scalar có API danh sách như **getSamplesList()**, **addSamples(...)**, không có **hasSamples()**. Nếu một thao tác cập nhật cần phân biệt "không thay đổi danh sách" với "xóa toàn bộ danh sách", hãy thiết kế yêu cầu cập nhật có mặt nạ field (**FieldMask**) hoặc cấu trúc điều khiển riêng.

## 7. Hợp đồng telemetry dùng scalar trong một RPC Spring gRPC

Giả sử một thiết bị gửi số đo đến backend Spring gRPC. Mỗi field dưới đây có mục đích rõ ràng:

~~~proto
syntax = "proto3";

package learning.telemetry.v1;

option java_package = "com.example.telemetry.v1";
option java_multiple_files = true;

message SubmitReadingRequest {
  string device_id = 1;
  uint64 sequence_id = 2;
  sint32 temperature_delta_milli_c = 3;
  double voltage = 4;
  optional bool calibrated = 5;
  bytes raw_payload = 6;
  repeated float samples = 7;
}

message SubmitReadingResponse {
  bool accepted = 1;
  string receipt_id = 2;
}

service TelemetryService {
  rpc SubmitReading(SubmitReadingRequest)
      returns (SubmitReadingResponse);
}
~~~

Phân tích lựa chọn:

- **device_id** dùng **string** vì là mã định danh văn bản, không phải số để tính toán.
- **sequence_id** dùng **uint64** nhằm biểu diễn bộ đếm không âm có miền lớn; phía Java cần chú ý cách nhìn không dấu.
- **temperature_delta_milli_c** dùng **sint32** vì sai lệch nhiệt độ thường là giá trị âm/dương quanh 0; tên field nêu rõ đơn vị milli-độ C.
- **voltage** dùng **double** vì là số đo thực, nhưng server vẫn phải kiểm tra yêu cầu hữu hạn và phạm vi nghiệp vụ.
- **calibrated** dùng **optional bool** vì bên nhận phải biết cờ hiệu chuẩn có thực sự được cung cấp hay không.
- **raw_payload** chứa byte từ thiết bị; **samples** chứa nhiều mẫu **float** mà thứ tự lấy mẫu có thể quan trọng.

### Sinh mã và sử dụng Java

Khi bước sinh mã đã được cấu hình với **protoc**, plugin Java và plugin gRPC Java, bạn sẽ có các lớp như **SubmitReadingRequest**, **SubmitReadingResponse** và **TelemetryServiceGrpc** trong package **com.example.telemetry.v1**. Cách cấu hình plugin build phụ thuộc dự án; schema quyết định kiểu và phương thức Java, còn Spring gRPC đảm nhận việc gắn client/server với kênh gRPC.

~~~java
import com.example.telemetry.v1.SubmitReadingRequest;
import com.google.protobuf.ByteString;

long sequence = Long.parseUnsignedLong("18446744073709551615");

SubmitReadingRequest request = SubmitReadingRequest.newBuilder()
    .setDeviceId("sensor-7")
    .setSequenceId(sequence)
    .setTemperatureDeltaMilliC(-125)
    .setVoltage(3.3d)
    .setCalibrated(false) // Có mặt dù giá trị là false.
    .setRawPayload(ByteString.copyFrom(new byte[] {0x01, 0x02}))
    .addSamples(1.25f)
    .addSamples(2.50f)
    .build();

System.out.println(request.getDeviceId()); // sensor-7
System.out.println(Long.toUnsignedString(request.getSequenceId()));
// 18446744073709551615
System.out.println(request.hasCalibrated()); // true
System.out.println(request.getCalibrated());  // false
System.out.println(request.getSamplesCount()); // 2
~~~

Builder chấp nhận **long** cho **uint64** vì nó lưu mẫu bit 64-bit. Khi gửi qua gRPC, phía nhận giải mã cùng số bit và có thể dùng **Long.toUnsignedString(...)** để hiển thị chính xác. Không dùng **String.valueOf(request.getSequenceId())** nếu cần hiển thị ý nghĩa không dấu.

Bạn có thể xác nhận round-trip của Protobuf mà chưa cần khởi động server:

~~~java
import static org.junit.jupiter.api.Assertions.*;

SubmitReadingRequest decoded =
    SubmitReadingRequest.parseFrom(request.toByteArray());

assertEquals(request, decoded);
assertEquals("18446744073709551615",
    Long.toUnsignedString(decoded.getSequenceId()));
assertEquals(-125, decoded.getTemperatureDeltaMilliC());
assertTrue(decoded.hasCalibrated());
assertFalse(decoded.getCalibrated());
assertEquals(2, decoded.getRawPayload().size());
~~~

### Kiểm tra dữ liệu tại server

Các kiểu scalar chỉ giới hạn cách biểu diễn; **chúng không tự bảo đảm dữ liệu hợp lệ về nghiệp vụ**. Ví dụ, một **double** có thể là NaN và một **string** có thể là chuỗi rỗng. Phần xử lý RPC bên dưới minh họa cách server từ chối input sai:

~~~java
import com.example.telemetry.v1.SubmitReadingRequest;
import com.example.telemetry.v1.SubmitReadingResponse;
import com.example.telemetry.v1.TelemetryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class TelemetryEndpoint
        extends TelemetryServiceGrpc.TelemetryServiceImplBase {

    @Override
    public void submitReading(SubmitReadingRequest request,
            StreamObserver<SubmitReadingResponse> observer) {
        if (request.getDeviceId().isBlank()
                || !Double.isFinite(request.getVoltage())
                || request.getSamplesCount() > 1000) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("Invalid telemetry reading")
                .asRuntimeException());
            return;
        }

        SubmitReadingResponse response = SubmitReadingResponse.newBuilder()
            .setAccepted(true)
            .setReceiptId("receipt-42")
            .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}
~~~

Lớp endpoint này minh họa phần xử lý request/response đã sinh từ .proto. Để chạy trong ứng dụng Spring gRPC, cần đăng ký và cấu hình dịch vụ theo cơ chế của phiên bản thư viện Spring gRPC mà dự án sử dụng. Những yêu cầu như kiểm tra metadata, deadline, status chi tiết, interceptor, TLS, streaming, giới hạn kích thước message, xác thực và giám sát độ tin cậy được cấu hình thêm ở lớp ứng dụng/giao thức tương ứng.

## 8. Scalar trong Protobuf JSON không luôn giống JSON "thông thường"

gRPC thường dùng Protobuf nhị phân. Tuy nhiên, khi giao tiếp qua gRPC JSON transcoding, ghi log có kiểm soát hoặc chuyển đổi với **google.protobuf.util.JsonFormat**, bạn cần biết **Protobuf JSON mapping**:

| Scalar | Dạng JSON theo Protobuf | Điểm cần chú ý |
| --- | --- | --- |
| **int32/sint32/uint32/fixed32/sfixed32** | JSON number | Bên nhận vẫn phải kiểm tra miền 32-bit và signed/unsigned |
| **int64/sint64/uint64/fixed64/sfixed64** | Chuỗi số thập phân | Giúp tránh mất chính xác khi JSON được đọc bởi hệ dùng số thực 64-bit, ví dụ JavaScript |
| **float/double** | JSON number | **NaN**, **Infinity**, **-Infinity** được biểu diễn dưới dạng chuỗi đặc biệt theo Protobuf JSON |
| **bool** | **true** hoặc **false** | Không đồng nghĩa với "đã gửi" nếu field không có presence |
| **string** | JSON string | Nội dung văn bản Unicode |
| **bytes** | JSON string Base64 | Không phải biểu diễn byte dưới dạng mảng số |

Ví dụ JSON tương ứng với request telemetry ở trên có dạng:

~~~json
{
  "deviceId": "sensor-7",
  "sequenceId": "18446744073709551615",
  "temperatureDeltaMilliC": -125,
  "voltage": 3.3,
  "calibrated": false,
  "rawPayload": "AQI=",
  "samples": [1.25, 2.5]
}
~~~

Tên field trong JSON thường được đổi sang **lowerCamelCase** theo mapping mặc định (**sequence_id** thành **sequenceId**). **rawPayload** là Base64 của hai byte **01 02**; **sequenceId** là chuỗi do thuộc họ 64-bit. **calibrated: false** xuất hiện khi field **optional bool** đã được đặt tường minh.

Nếu dùng các thư viện JSON tổng quát để serialize trực tiếp một lớp Protobuf Java, kết quả có thể không tuân theo Protobuf JSON mapping. Hãy sử dụng **JsonFormat** hoặc cơ chế chuyển đổi Protobuf chuyên dụng khi cần chuyển qua lại giữa hai định dạng. Tránh dùng dạng JSON trong log làm bằng chứng về việc một scalar implicit presence đã được bên gửi đặt hay chưa.

## 9. Các lỗi điển hình khi làm việc với scalar

| Tình huống | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem **uint64** trả về **long** âm là lỗi dữ liệu | Hiển thị/so sánh sai số không dấu | Dùng **Long.toUnsignedString**, **Long.compareUnsigned** |
| Dùng **int32** cho số đếm có thể vượt 2.147.483.647 | Tràn miền và sai nghiệp vụ | Chọn **uint32** hoặc loại 64-bit theo miền thực |
| Dùng **int32** cho nhiều sai lệch âm nhỏ | Payload varint thường lớn hơn cần thiết | Cân nhắc **sint32** cho schema mới |
| Dùng **float** để tính tiền | Sai số khi cộng/trừ/so sánh | Dùng đơn vị tiền nhỏ nhất dạng integer hoặc kiểu decimal chuyên dụng |
| Dùng **bytes** rồi mặc định gọi **toStringUtf8()** | Diễn giải byte nhị phân thành văn bản sai | Giải mã theo định dạng payload đã thỏa thuận |
| Dựa vào **getEnabled() == false** để suy ra client đã gửi false | Nhầm vắng mặt với giá trị mặc định | Dùng **optional bool** hoặc cơ chế cập nhật tường minh |
| Đổi **int32** thành **sint32** trên cùng số field | Bản cũ và bản mới đọc ra giá trị khác | Thêm field mới; giữ quy tắc versioning và reserve |
| Dùng **String.valueOf(uint64Long)** để ghi số không dấu | Ghi số âm cho giá trị lớn | Dùng chuyển đổi không dấu |
| Giả định **double** chỉ nhận số hữu hạn | NaN/Infinity lọt qua quy tắc nghiệp vụ | Kiểm tra **Double.isFinite** |
| Đưa integer 64-bit trực tiếp vào JSON number cho JavaScript | Có thể mất độ chính xác | Tuân thủ Protobuf JSON mapping dùng chuỗi thập phân |

Việc chọn scalar cũng ảnh hưởng đến **hiệu năng và độ tin cậy**. Tuy nhiên, tối ưu băng thông cần đo với dữ liệu thật, bao gồm tần suất field xuất hiện, chi phí tag, kiểu RPC và chính sách nén; không nên đổi hợp đồng sản xuất chỉ dựa vào bảng kích thước lý thuyết.

## 10. Bài tập thực hành

Thiết kế message **UpdateSensorConfigRequest** cho một endpoint gRPC với các yêu cầu sau:

1. **sensor_id** là mã văn bản không được để trống.
2. **retry_limit** là số nhỏ, luôn không âm; trình bày lý do chọn **int32** hoặc **uint32**.
3. **calibration_shift_milli_c** là độ lệch nhiệt độ có thể âm/dương quanh 0; chọn kiểu số tiết kiệm dung lượng phù hợp.
4. **firmware_version** là chuỗi ký tự; **firmware_blob** là dữ liệu firmware nhị phân. Giải thích tại sao không đảo kiểu hai field.
5. **enabled** phải phân biệt "không cập nhật" với "đặt false". Khai báo field với explicit presence và kiểm tra **hasEnabled()** sau serialize/parse.
6. **max_sequence_id** cần chấp nhận số **18.446.744.073.709.551.615**; viết Java code để đặt giá trị và in ra dưới dạng số không dấu.
7. **recent_samples** là tập mẫu đo có thứ tự. Chọn **repeated float** hoặc **repeated double** và giải thích độ chính xác/chi phí.

Một phác thảo schema hợp lệ:

~~~proto
syntax = "proto3";

message UpdateSensorConfigRequest {
  string sensor_id = 1;
  uint32 retry_limit = 2;
  sint32 calibration_shift_milli_c = 3;
  string firmware_version = 4;
  bytes firmware_blob = 5;
  optional bool enabled = 6;
  uint64 max_sequence_id = 7;
  repeated float recent_samples = 8;
}
~~~

Thử tạo hai đối tượng **UpdateSensorConfigRequest**, một đối tượng **không gọi setEnabled(...)**, đối tượng kia gọi **setEnabled(false)**. Trước và sau **parseFrom(toByteArray())**, xác nhận getter đều cho **false** nhưng chỉ đối tượng thứ hai có **hasEnabled() == true**. Sau đó dùng **Long.parseUnsignedLong(...)** và **Long.toUnsignedString(...)** với **max_sequence_id** để kiểm tra giá trị cực đại.

**Tự đánh giá:** nếu cùng là Java **int**, bạn có giải thích được vì sao **int32** khác **uint32**, **sint32** và **fixed32** không? Nếu một giá trị không xuất hiện trong request, bạn có nhận biết được đó là mặc định implicit hay một giá trị đã được gửi tường minh không? Trả lời được hai câu này là nền tảng để đọc đúng request/response Protobuf và thiết kế hợp đồng Spring gRPC ổn định.
