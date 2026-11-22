# Thiết kế phần đầu, loại thông điệp, độ dài và phiên bản giao thức trên TCP

## 1. Mục tiêu: biến dòng byte TCP thành những thông điệp có ý nghĩa

TCP cung cấp cho hai đầu kết nối một **dòng byte có thứ tự**. TCP không biết khái niệm “thông điệp nghiệp vụ số 1”, “thông điệp nghiệp vụ số 2”, JSON object, hay một lời gọi API. Nếu phía gửi gọi `OutputStream.write(frameA)` rồi `write(frameB)`, phía nhận có thể thấy nửa `frameA` ở lần `read` đầu, phần còn lại ở lần sau, hoặc cùng lúc nhiều frame. Ranh giới của các lần `write` **không trở thành ranh giới của các lần `read`**; TCP có thể phân mảnh hoặc gộp dữ liệu tùy kết quả truyền và bộ đệm.

Ví dụ một client gửi hai thông điệp logic:

```text
Thông điệp A: DATA("Xin chào")
Thông điệp B: PING()
```

Phía nhận có thể thấy các lần đọc tùy ý như:

```text
read #1: [nửa header A]
read #2: [header A còn lại][một phần payload A]
read #3: [payload A còn lại][toàn bộ header B]
read #4: [có thể là phần tiếp theo hoặc chưa có dữ liệu]
```

Nếu lấy mỗi lần `InputStream.read(...)` làm một message thì parser sẽ hỏng. **Giao thức tầng ứng dụng phải tự xác định điểm bắt đầu, kích thước và ý nghĩa của từng thông điệp**. Công việc này được gọi là *message framing*.

Bài này tập trung vào bốn quyết định cốt lõi: **phần đầu (header), loại thông điệp (message type), độ dài (length), phiên bản giao thức (protocol version)**. Mục tiêu là xây dựng một hợp đồng có thể giải mã độc lập với việc TCP chia nhỏ/gộp dữ liệu, đồng thời cho phép các phiên bản phần mềm giao tiếp có kiểm soát.

Sau bài học, bạn sẽ:
- Mô tả ranh giới frame rõ ràng và phân biệt frame với TCP segment.
- Thiết kế cấu trúc header nhị phân có *magic*, version, type, flags, correlation ID và payload length, kèm offset, endian, ràng buộc.
- Biết khi nào chọn fixed-length, delimiter, length-prefix hoặc cấu trúc mở rộng TLV.
- Viết encoder/decoder Java 17+ đọc đủ header và payload, chặn độ dài nguy hiểm, phát hiện EOF giữa frame.
- Quy định thông điệp DATA/ACK/ERROR/PING, khả năng tương thích phiên bản, xử lý thông điệp không hiểu và kiểm thử.

## 2. Tách ba khái niệm: byte, frame và thông điệp nghiệp vụ

| Khái niệm | Thuộc lớp nào? | Điều cần nhớ |
| --- | --- | --- |
| TCP segment | TCP / mạng | Có header TCP; biên segment không phải biên message nghiệp vụ |
| Byte stream | API socket | `InputStream`/`OutputStream` giao các byte theo thứ tự, lượng byte mỗi lần đọc không cố định |
| Frame | Giao thức ứng dụng do chúng ta định nghĩa | Một đơn vị được xác định qua header và độ dài payload |
| Message type | Giao thức ứng dụng | Cho biết phải hiểu payload theo schema/luồng xử lý nào |
| Request / response | Nghiệp vụ | Có thể ánh xạ nhiều message vào một kết nối; cần ID nếu ghép kết quả bất đồng bộ |

Ví dụ với *length-prefixed framing*:

```text
TCP byte stream
┌───────────────────────────┬────────────────────┬───────────────────────┐
│ header A │ payload A      │ header B │ payload B│ header C │ payload C  │
└───────────────────────────┴────────────────────┴───────────────────────┘
         ↑ một frame                    ↑ frame tiếp theo
```

Một frame có thể đi qua nhiều segment; ngược lại, một segment có thể chứa nhiều frame. Decoder giữ thứ tự dòng byte và cắt từng frame dựa vào hợp đồng header, **không** đoán theo ranh giới gói mạng.

Khái niệm **TCP ACK** khác **ACK nghiệp vụ**: TCP ACK thể hiện cơ chế xác nhận byte tại tầng TCP; một thông điệp `ACK` do ứng dụng gửi có thể mang ý nghĩa “đã nhận và xử lý request số 42” theo hợp đồng riêng. Chỉ thấy TCP gửi thành công **không** chứng minh nghiệp vụ đã commit.

## 3. Những phương án tạo ranh giới message

| Phương án | Cách phân định | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Độ dài cố định | Mỗi frame có đúng N byte | Parser đơn giản, offset cố định | Lãng phí với payload thay đổi; khó mở rộng |
| Delimiter, ví dụ `\n` | Đọc đến ký tự kết thúc | Phù hợp giao thức dòng văn bản | Phải escape nếu delimiter xuất hiện trong dữ liệu; giới hạn độ dài dòng |
| Tiền tố độ dài | Header chứa số byte payload | Hỗ trợ payload nhị phân và kích thước thay đổi | Phải kiểm tra length trước cấp phát; phải đọc đúng số byte |
| Header + length + type | Header có metadata, body dài tùy biến | Dễ định tuyến message, versioning và tương quan request | Cần đặc tả byte-level đầy đủ |
| Varint length / TLV | Độ dài hoặc field được mã hóa linh hoạt | Có thể tiết kiệm byte/mở rộng | Parser phức tạp hơn, cần giới hạn và quy tắc tương thích |

Bài này chọn **header cố định 16 byte + payload có độ dài khai báo** để minh họa đầy đủ bốn khía cạnh. Đây là một giao thức mẫu phục vụ học tập, **không phải chuẩn wire protocol phổ biến có tên “JMSG”**. Các hệ thống thực có thể chọn HTTP/2, gRPC, WebSocket, MQTT, Redis RESP hoặc Protobuf framing tùy nhu cầu; không nên tự xây lại giao thức nếu chuẩn sẵn có đã đáp ứng.

**Điều kiện tiên quyết khi chọn framing:** hai phía phải thống nhất kích thước header, thứ tự byte (endian), cách đọc số không dấu, kiểu dữ liệu payload, giới hạn độ dài và cách phản ứng khi dữ liệu sai. Thiếu bất kỳ quyết định nào, hai bản cài đặt có thể giải mã khác nhau dù cùng nhận một chuỗi byte.

## 4. Đặc tả giao thức minh họa: header 16 byte

Ta thiết kế định dạng v1.0:

```text
Offset (byte)     0           4   5   6   7          8          12       16
                  │           │   │   │   │          │           │        │
                  ▼           ▼   ▼   ▼   ▼          ▼           ▼        ▼
Frame =          [MAGIC:4][MAJ:1][MIN:1][TYPE:1][FLAGS:1][REQUEST_ID:4][LENGTH:4][PAYLOAD:LENGTH]
                  └──────────────── header = 16 bytes ──────────────────┘
```

| Offset (tính từ đầu frame) | Độ rộng | Field | Diễn giải / quy tắc v1.0 |
| --- | ---: | --- | --- |
| `0..3` | 4 byte | `magic` | Hằng 0x4A4D5347, ASCII “JMSG”; kiểm tra sai header/giao thức |
| `4` | 1 byte | `versionMajor` | `1`; bản major không hỗ trợ → từ chối |
| `5` | 1 byte | `versionMinor` | `0` trong demo; bản minor khác cũng từ chối vì chưa có negotiation |
| `6` | 1 byte | `messageType` | `1` DATA, `2` ACK, `3` ERROR, `4` PING |
| `7` | 1 byte | `flags` | `0`; mọi bit còn lại chưa định nghĩa nên phải bằng 0 |
| `8..11` | 4 byte | `requestId` | Mã tương quan `uint32`, trên Java lưu bằng bit của `int` |
| `12..15` | 4 byte | `payloadLength` | Số **byte** của payload; v1.0 chỉ cho `0..1_048_576` |
| `16..` | `payloadLength` byte | `payload` | Dữ liệu theo schema của từng type |

**Thứ tự byte:** tất cả field số dài nhiều byte được ghi **big-endian** (network byte order). Đây là quy tắc do giao thức quy định; không phụ thuộc CPU chạy little-endian hay big-endian. Trong Java, `DataOutputStream.writeInt` ghi byte có trọng số cao trước; `ByteBuffer.order(ByteOrder.BIG_ENDIAN)` giải mã nhất quán.

**Độ rộng trường:** tổng là `4 + 1 + 1 + 1 + 1 + 4 + 4 = 16` byte. Một frame rỗng (như PING) vẫn tốn 16 byte header. Nếu payload có N byte, frame dài chính xác `16 + N` byte. `payloadLength` **không bao gồm** 16 byte header trong giao thức này.

**Giới hạn 1 MiB:** là một quy tắc ví dụ, không phải giới hạn TCP. Bộ giải mã phải từ chối length lớn hơn trước khi tạo mảng, kể cả khi field trên wire có thể biểu diễn số lớn hơn. Nếu protocol muốn frame lớn hơn trong hệ thống khác, phải đo lường bộ nhớ, deadline, concurrency, backpressure và cơ chế streaming.

### 4.1. Tại sao cần magic?

`magic` giúp phát hiện đầu stream không dùng protocol này hoặc header bị hỏng. Với 4 byte “JMSG”, xác suất trùng ngẫu nhiên thấp hơn việc chỉ dựa vào một byte type. Tuy nhiên:
- Magic **không xác thực** người gửi.
- Magic **không phải checksum hay chữ ký số**.
- Khi phát hiện sai magic, v1.0 chủ động **đóng kết nối**, không tự dò chuỗi “JMSG” tiếp theo: trong dữ liệu không đáng tin, phép scan có thể nhầm magic nằm trong payload và khiến parser lệch khung.

### 4.2. Tại sao cần requestId?

TCP bảo toàn thứ tự byte nhưng không tự chỉ ra response nào thuộc request nào khi ứng dụng có nhiều tác vụ đang chờ. Trường `requestId` giúp client ghép kết quả, theo dõi timeout và đối chiếu log.

Quy tắc v1.0:
- `DATA`, `ACK`, `ERROR` có `requestId != 0`.
- `PING` là kiểm tra liveness một chiều, có `requestId == 0`, payload rỗng.
- `ACK` mang lại cùng ID của `DATA` được xác nhận.
- `requestId` 32 bit là **opaque identifier**, không phải chứng chỉ bảo mật hay bằng chứng exactly-once. Khi số tăng hết miền, cần chính sách quay vòng và tránh trùng ID đang hoạt động.

## 5. Ví dụ biểu diễn từng byte trên wire

Gửi DATA (`type=1`), version 1.0, `flags=0`, requestId `42`, payload UTF-8 `Xin chào`.

UTF-8 của `Xin chào` chiếm **9 byte**, dù chuỗi có **8 ký tự Unicode**. Payload là:

```text
58 69 6E 20 63 68 C3 A0 6F
 X  i  n     c  h    à     o
```

Header 16 byte:

```text
4A 4D 53 47 | 01 | 00 | 01 | 00 | 00 00 00 2A | 00 00 00 09
    JMSG     major minor type flags requestId=42  payloadLength=9
```

Cả frame = 16 byte header + 9 byte payload = **25 byte**. Ký tự `à` mã hóa thành `C3 A0`; nếu sender ghi length bằng `String.length() == 8`, decoder chỉ lấy 8 byte, bỏ lại byte `6F` thành “rác” trước header kế tiếp và giao thức mất đồng bộ.

Đây cũng là lý do không dùng “số ký tự” hay “số object” thay cho `payloadLength`. Hãy mã hóa payload trước, lấy `byteArray.length`, sau đó ghi header và đúng mảng byte đó.

## 6. Định nghĩa message type như một hợp đồng nghiệp vụ

Mục tiêu type không chỉ để định tuyến đến một `switch`. Cần đặc tả rõ **ai được gửi, payload có schema gì, phản hồi có hay không, và điều kiện hợp lệ**.

| Type v1.0 | Giá trị | Payload | requestId | Ý nghĩa demo |
| --- | ---: | --- | --- | --- |
| `DATA` | 1 | Nội dung UTF-8, độ dài ≤ 1 MiB | Khác 0 | Client gửi dữ liệu; demo không quy định schema nghiệp vụ sâu hơn |
| `ACK` | 2 | Thông tin xác nhận (ví dụ `OK`) | Trùng request đã nhận | Server xác nhận đã xử lý theo quy tắc ứng dụng |
| `ERROR` | 3 | Mã lỗi + diễn giải theo schema đã công bố | Trùng request lỗi | Trả lỗi nghiệp vụ mà kết nối vẫn có thể hợp lệ |
| `PING` | 4 | Bắt buộc rỗng | Bắt buộc 0 | Tín hiệu liveness do giao thức mẫu định nghĩa |

Demo ở mục 11 chỉ gửi `DATA`, `PING` và `ACK`; `ERROR` có định danh nhưng chưa định nghĩa chi tiết payload encoding. **Không tự cho rằng nội dung ERROR là JSON hay UTF-8 có cấu trúc ổn định** trước khi đặc tả schema. Trong ứng dụng thật cần rõ:
- Payload của mỗi type dùng UTF-8, JSON, CBOR, Protobuf hay định dạng nào?
- Có trường bắt buộc, trường tùy chọn, giới hạn độ dài và validation gì?
- Server trả `ACK` lúc “đã nhận vào buffer”, “đã lưu”, hay “đã commit giao dịch”? Ba thời điểm khác nhau.
- Request trùng ID do retry sẽ bị từ chối, trả lại kết quả cũ hay được xử lý lại? Correlation ID không tự bảo đảm **idempotency**.
- Có cho nhiều request đồng thời trên một kết nối không? Nếu có, một reader phải parse tuần tự byte stream rồi định tuyến response cho request tương ứng bằng ID; hai luồng không nên đồng thời tự `readFrame` từ cùng `InputStream`.

**Loại chưa được hỗ trợ:** demo reject mọi `type` ngoài `1..4`. Đây là lựa chọn fail-closed của bản v1.0. Một giao thức lớn hơn có thể định nghĩa khoảng type tùy chọn, nhưng phải quy định liệu client cũ có bỏ qua an toàn không và cách thương lượng capability.

## 7. Phiên bản giao thức: tránh “parse được” nhưng hiểu sai

Header có hai byte `major` và `minor`. Ý nghĩa được đề xuất:

- **Major** thay đổi khi wire format hoặc semantics bị phá vỡ: đổi offset/độ rộng header, đổi endian, đổi cách diễn giải length, đổi trường bắt buộc hoặc thay đổi hành vi message type không tương thích.
- **Minor** dự kiến dùng cho bổ sung tương thích, nhưng chỉ khi protocol thực sự định nghĩa cơ chế đọc field mới, bỏ qua phần tùy chọn và capability negotiation.
- **Patch version** nếu có thường thuộc release phần mềm, không cần xuất hiện trong wire header trừ khi protocol có lý do.

Trong **bản demo hiện tại**, decoder chỉ nhận cặp **(major=1, minor=0)**. Điều này có chủ đích: chưa có thương lượng version hoặc cơ chế “bỏ qua optional field”, nên tự động chấp nhận minor bất kỳ là hứa một mức tương thích mà code chưa bảo đảm.

### 7.1. Khi triển khai nhiều phiên bản cùng lúc

Giả sử server v2 muốn thêm compression hoặc message type mới. Các bước nên cân nhắc:
1. Xác định thay đổi có tương thích với khung 16 byte và parser cũ không.
2. Nếu có optional extension, thiết kế rõ **cách xác định độ dài extension**, namespace/type của TLV và quy tắc “field nào bắt buộc phải hiểu”.
3. Nếu thay đổi phá hợp đồng, tăng `major` và chọn giải pháp nâng cấp/phân tuyến hoặc endpoint cũ–mới.
4. Nếu muốn cùng một kết nối hỗ trợ nhiều capability, có thể thêm handshake `HELLO`/`HELLO_ACK` (và type tương ứng được định nghĩa chính thức trong revision mới) trao đổi danh sách version/feature trước dữ liệu nghiệp vụ.
5. Triển khai theo thứ tự tránh downtime: server hỗ trợ cả bản cũ/mới trước; client chuyển dần; có telemetry về phân bố version; loại bỏ bản cũ sau khi không còn caller.

**Không dùng `minor` như cái cớ để âm thầm tái định nghĩa trường cũ.** Ví dụ nếu v1.0 hiểu bit 0 của flags là “reserved=0” mà v1.1 đổi bit đó thành “compressed”, client cũ có thể từ chối hoặc giải mã body sai. Cần negotiation và quy tắc flag rõ ràng; nếu không, coi đây là thay đổi không tương thích.

### 7.2. Ví dụ thiết kế mở rộng (chưa được v1.0 hỗ trợ)

Một revision khác có thể thêm `headerLength` cùng các TLV sau header cơ sở:

```text
[type:1][length:2][value:length] ...
```

Nhưng để an toàn phải đồng thời giới hạn tổng độ dài extension, quy định thứ tự/duplicate TLV, cách skip unknown optional TLV, xử lý unknown required TLV, endian và số field tối đa. **Giao thức 16-byte v1.0 ở bài này không có trường `headerLength` và không có TLV**; biểu diễn trên chỉ là phương án cho bản thiết kế mới, không được tự nối vào frame mẫu.

## 8. Flags và định dạng payload phải được quy định tường minh

Trong header v1.0, `flags` có 8 bit nhưng mọi bit đều reserved và bắt buộc bằng 0. Tại sao không “bỏ qua flags lạ”?
- Một peer mới có thể đặt bit báo body nén, mã hóa hay cần checksum; peer cũ bỏ qua sẽ diễn giải byte sai.
- Bit có thể thay đổi semantics của field khác; nếu không hiểu, tiếp tục là không an toàn.
- Từ chối rõ ràng tạo lỗi tương thích dễ chẩn đoán thay vì corrupt dữ liệu im lặng.

Khi thật sự cần flags, hãy công bố bảng bit như `COMPRESSED=0x01`, `CHECKSUM_PRESENT=0x02` cùng điều kiện chọn thuật toán, độ dài sau giải nén, cơ chế negotiation, và cách xử lý khi không hỗ trợ. Đừng dành bit cho tương lai rồi tự suy diễn nghĩa trong một phiên bản chưa đặc tả.

### 8.1. Cấu trúc payload độc lập với framing

Header biết `type` và `length`; nó **không tự làm payload trở thành JSON, object Java hay text Unicode**. Nếu DATA dùng UTF-8 thì hai phía cần thống nhất:
- Charset cố định `UTF-8`.
- Schema/field bắt buộc và cấu trúc phiên bản payload nếu payload có object.
- Giới hạn kích thước, nesting, trường không biết và hành vi khi payload sai.
- Đối với JSON: quy tắc duplicate key, số, Unicode, an toàn parser và giới hạn độ sâu.
- Nếu dùng Protobuf/CBOR: version schema và định dạng wire chính thức của chúng, còn header bên ngoài chỉ dùng cho framing/dispatch.

Đừng dùng `DataOutputStream.writeUTF` thay cho UTF-8 thuần mà không nói rõ: API này ghi **modified UTF-8** kèm 2 byte length, khác `"text".getBytes(StandardCharsets.UTF_8)`. Ví dụ bên dưới dùng **UTF-8 thuần**.

## 9. Luồng giải mã đúng: header → kiểm tra → payload

Một decoder đúng cần tuân theo thứ tự:

```text
Ở đầu frame
    │
    ├─ read 1 byte đầu tiên == -1? ──► EOF sạch (không còn frame)
    ▼
Đọc đủ 16 byte header (không giả định 1 read lấy đủ)
    │
    ├─ EOF giữa header? ─────────────► LỖI frame bị cắt
    ▼
Kiểm tra magic, major/minor, type, flags, requestId
    │
    ├─ Không khớp? ──────────────────► LỖI protocol / đóng kết nối
    ▼
Kiểm tra 0 <= payloadLength <= MAX_PAYLOAD
    │
    ├─ Âm hoặc vượt max? ────────────► LỖI trước khi cấp phát
    ▼
Cấp phát buffer đúng length và đọc đủ payload
    │
    ├─ EOF giữa payload? ────────────► LỖI frame bị cắt
    ▼
Dispatch frame theo type/schema/requestId
    │
    ▼
Lặp lại tại đầu frame tiếp theo
```

Ở đây có sự khác biệt thiết yếu:
- Nếu vừa kết thúc một frame hợp lệ rồi `InputStream.read()` trả `-1` **ở đầu frame tiếp theo**, đó là kết thúc dòng byte sạch.
- Nếu đã thấy ít nhất một byte của header mà phần còn lại không đến trước EOF, đó là **truncated header**.
- Nếu header nói body dài 9 byte nhưng chỉ đến 8 byte rồi EOF, đó là **truncated payload**.
- Nếu header nói body dài hơn giới hạn, reject **trước** khi tạo mảng byte hoặc đợi nhận đủ.

`DataInputStream.readFully(byte[])` chỉ trả về khi buffer được điền đủ, hoặc ném `EOFException` nếu EOF đến sớm. Nó **không** xem một lần `read` là một message. Nhưng `readFully` cũng có thể chờ lâu nếu peer gửi rất chậm; production cần deadline, timeout và giới hạn tài nguyên.

### 9.1. Endian và số không dấu trong Java

Java `byte` có dấu (`-128..127`). Đọc một field 1 byte mang giá trị unsigned cần `Byte.toUnsignedInt(byteValue)`. Đối với `requestId` kiểu `uint32`, Java `int` chỉ lưu cùng 32 bit; nếu muốn in theo dạng unsigned, dùng `Integer.toUnsignedString(id)`. Vì requestId chỉ là mã đối chiếu, giữ nguyên bits khi echo là đủ.

`payloadLength` trên wire được thiết kế dạng `uint32`, nhưng decoder Java đọc vào `int`: nếu bit cao bằng 1, giá trị Java sẽ âm. Do giới hạn demo ≤ 1 MiB, **mọi giá trị âm đều vượt giới hạn hợp lệ** và phải reject. Không cộng `16 + length` vào `int` **trước** khi xác minh length để tránh overflow hoặc cấp phát ngoài ý muốn.

## 10. Encoder phải tạo frame hoàn chỉnh theo một hợp đồng

Encoder thực hiện đối xứng:

1. Xác minh `type`, requestId, payload không null và length ≤ giới hạn.
2. Mã hóa payload ra **byte[]** trước (ví dụ UTF-8).
3. Ghi magic 4 byte, major, minor, type, flags, requestId 4 byte và payload length 4 byte theo big-endian.
4. Ghi đúng `payloadLength` byte body.
5. Flush theo yêu cầu ứng dụng hoặc quản lý buffer thích hợp, nhưng không coi một lần `flush` là một frame hoặc một TCP packet.

Khi nhiều luồng cùng gửi lên một socket, phải serialize **toàn bộ header + body của từng frame** bằng một single writer/queue hoặc lock chung. Nếu thread A ghi nửa header A rồi thread B ghi header B, byte stream bị xen kẽ và không thể decode đúng. Một `writeFrame` đúng trên từng luồng **không đủ** nếu các luồng không phối hợp sử dụng cùng `OutputStream`.

**Thứ tự frame:** TCP giữ thứ tự byte từ một connection, nên decoder sẽ đọc A trước B nếu encoder thực sự ghi trọn A rồi mới ghi B. Tuy nhiên đây không phải ordering của *nghiệp vụ phân tán*: server có thể xử lý request song song, trả response theo thứ tự khác; requestId giúp ghép kết quả.

## 11. Chương trình Java 17+: codec nhị phân và trao đổi qua TCP loopback

Đây là **một file Java độc lập**, không dùng thư viện bên ngoài. Chương trình có hai phần:
- **Memory test:** tạo hai frame liên tiếp trong một dòng byte, giả lập mỗi bulk `read` chỉ trả tối đa 3 byte, kiểm tra EOF sạch, payload bị cắt và header khai độ dài vượt giới hạn.
- **Socket test:** mở server loopback trên cổng ngẫu nhiên, client gửi DATA rồi PING trên **một kết nối TCP**, server đọc hai frame và trả ACK cùng requestId.

Lưu file `TcpFrameDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicReference;

public class TcpFrameDemo {
    private static final int MAGIC = 0x4A4D5347; // "JMSG"
    private static final int HEADER_BYTES = 16;
    private static final int MAX_PAYLOAD = 1_048_576;
    private static final int DATA = 1, ACK = 2, ERROR = 3, PING = 4;

    record Frame(int type, int requestId, byte[] payload) {
        Frame {
            if (payload == null) throw new IllegalArgumentException("payload");
            payload = payload.clone();
        }
        @Override public byte[] payload() {
            return payload.clone();
        }
    }

    private static void validateFields(int type, int requestId, int length)
            throws IOException {
        if (type < DATA || type > PING) throw new IOException("type");
        if (length < 0 || length > MAX_PAYLOAD) throw new IOException("length");
        if (type == PING && (requestId != 0 || length != 0)) {
            throw new IOException("ping");
        }
        if (type != PING && requestId == 0) {
            throw new IOException("requestId");
        }
    }

    static void writeFrame(OutputStream stream, Frame frame) throws IOException {
        byte[] bytes = frame.payload();
        validateFields(frame.type(), frame.requestId(), bytes.length);
        DataOutputStream out = new DataOutputStream(stream);
        out.writeInt(MAGIC);
        out.writeByte(1); // major
        out.writeByte(0); // minor
        out.writeByte(frame.type());
        out.writeByte(0); // flags reserved
        out.writeInt(frame.requestId());
        out.writeInt(bytes.length);
        out.write(bytes);
        out.flush();
    }

    static Frame readFrame(InputStream stream) throws IOException {
        DataInputStream in = new DataInputStream(stream);
        int firstByte = in.read();
        if (firstByte == -1) return null; // clean EOF between frames

        byte[] header = new byte[HEADER_BYTES];
        header[0] = (byte) firstByte;
        in.readFully(header, 1, HEADER_BYTES - 1);

        ByteBuffer fields = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN);
        int magic = fields.getInt();
        int major = Byte.toUnsignedInt(fields.get());
        int minor = Byte.toUnsignedInt(fields.get());
        int type = Byte.toUnsignedInt(fields.get());
        int flags = Byte.toUnsignedInt(fields.get());
        int requestId = fields.getInt();
        int length = fields.getInt();

        if (magic != MAGIC) throw new IOException("magic");
        if (major != 1 || minor != 0) throw new IOException("version");
        if (flags != 0) throw new IOException("flags");
        validateFields(type, requestId, length);

        byte[] payload = new byte[length];
        in.readFully(payload);
        return new Frame(type, requestId, payload);
    }

    private static void memoryDemo() throws IOException {
        ByteArrayOutputStream wire = new ByteArrayOutputStream();
        writeFrame(wire, new Frame(DATA, 42,
                "Xin chào".getBytes(StandardCharsets.UTF_8)));
        writeFrame(wire, new Frame(PING, 0, new byte[0]));
        byte[] bytes = wire.toByteArray();
        System.out.println("HEADER=" + HexFormat.ofDelimiter(" ")
                .withUpperCase().formatHex(bytes, 0, HEADER_BYTES));

        InputStream fragmented = new FilterInputStream(new ByteArrayInputStream(bytes)) {
            @Override public int read(byte[] buffer, int offset, int length)
                    throws IOException {
                return super.read(buffer, offset, Math.min(length, 3));
            }
        };
        Frame first = readFrame(fragmented);
        Frame second = readFrame(fragmented);
        System.out.println("FRAME1=DATA id="
                + Integer.toUnsignedString(first.requestId())
                + " bytes=" + first.payload().length
                + " text=" + new String(first.payload(), StandardCharsets.UTF_8));
        System.out.println("FRAME2=PING id=" + second.requestId()
                + " bytes=" + second.payload().length);
        System.out.println("EOF_AT_BOUNDARY=" + (readFrame(fragmented) == null));

        try {
            readFrame(new ByteArrayInputStream(
                    Arrays.copyOf(bytes, HEADER_BYTES + 3)));
            throw new AssertionError("must reject truncated body");
        } catch (EOFException expected) {
            System.out.println("TRUNCATED_BODY=EOFException");
        }
        byte[] oversized = Arrays.copyOf(bytes, HEADER_BYTES);
        ByteBuffer.wrap(oversized).order(ByteOrder.BIG_ENDIAN)
                .putInt(12, MAX_PAYLOAD + 1);
        try {
            readFrame(new ByteArrayInputStream(oversized));
            throw new AssertionError("must reject oversize");
        } catch (IOException expected) {
            System.out.println("OVERSIZE=" + expected.getMessage());
        }
    }

    private static void socketDemo() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(3000);
            AtomicReference<String> received = new AtomicReference<>("none");
            AtomicReference<Throwable> failure = new AtomicReference<>();
            Thread server = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3000);
                    Frame data = readFrame(peer.getInputStream());
                    Frame ping = readFrame(peer.getInputStream());
                    if (data == null || data.type() != DATA
                            || ping == null || ping.type() != PING) {
                        throw new IOException("unexpected frames");
                    }
                    received.set("DATA,PING");
                    writeFrame(peer.getOutputStream(), new Frame(
                            ACK, data.requestId(),
                            "OK".getBytes(StandardCharsets.UTF_8)));
                } catch (Throwable e) {
                    failure.set(e);
                }
            });
            server.start();
            try (Socket client = new Socket(
                    "127.0.0.1", listener.getLocalPort())) {
                client.setSoTimeout(3000);
                writeFrame(client.getOutputStream(), new Frame(
                        DATA, 42, "Xin chào".getBytes(StandardCharsets.UTF_8)));
                writeFrame(client.getOutputStream(), new Frame(
                        PING, 0, new byte[0]));
                Frame reply = readFrame(client.getInputStream());
                if (reply == null || reply.type() != ACK) {
                    throw new IOException("missing ACK");
                }
                System.out.println("CLIENT_ACK="
                        + Integer.toUnsignedString(reply.requestId())
                        + ":" + new String(reply.payload(), StandardCharsets.UTF_8));
            }
            server.join(5000);
            if (server.isAlive()) throw new IOException("server timeout");
            if (failure.get() != null) throw new IOException("server failed", failure.get());
            System.out.println("SERVER_RECEIVED=" + received.get());
        }
    }

    public static void main(String[] args) throws Exception {
        memoryDemo();
        socketDemo();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TcpFrameDemo.java
java TcpFrameDemo
```

Stdout của chương trình khi loopback socket hoạt động bình thường:

```text
HEADER=4A 4D 53 47 01 00 01 00 00 00 00 2A 00 00 00 09
FRAME1=DATA id=42 bytes=9 text=Xin chào
FRAME2=PING id=0 bytes=0
EOF_AT_BOUNDARY=true
TRUNCATED_BODY=EOFException
OVERSIZE=length
CLIENT_ACK=42:OK
SERVER_RECEIVED=DATA,PING
```

### 11.1. Decoder chịu được nhiều lần đọc

`FilterInputStream` trong ví dụ giới hạn mỗi lần gọi **bulk** `read(byte[], off, len)` xuống tối đa 3 byte. Nếu code giả định một lần đọc nhận đủ 16 byte, nó sẽ sai ngay; `DataInputStream.readFully` lặp đến đủ. Kết quả vẫn giải mã DATA và PING đúng, chứng minh framing không phụ thuộc cách dòng byte được chia.

Điều này chỉ mô phỏng **fragmented reads**, không phải kiểm thử mô hình phân mảnh packet TCP thực tế. Hành vi cần bảo đảm là decoder xử lý được **mọi phân hoạch hợp lệ của byte stream**, không phải “mỗi frame có một packet”.

### 11.2. Đầu stream, EOF và lỗi frame

`readFrame` đọc byte đầu tiên trước khi yêu cầu 15 byte tiếp theo để phân biệt:
- Không có byte nào ở đầu frame mới → trả `null` (EOF sạch).
- Có một vài byte header nhưng thiếu phần còn lại → `EOFException`.
- Header hoàn chỉnh nhưng payload còn thiếu → `EOFException`.
- Header báo length 1_048_577 → `IOException("length")` **trước cấp phát payload**.

Không được bắt mọi `EOFException` rồi coi như “không có message”, vì việc stream kết thúc giữa frame có nghĩa dữ liệu **không hoàn chỉnh**. Trong ứng dụng thật, thường nên log/đếm metric lỗi protocol và đóng kết nối.

### 11.3. Đồng bộ giữa client và server

Server nhận lần lượt `DATA` và `PING`, sau đó gửi `ACK` có requestId 42. Client đọc ACK trên cùng kết nối và so khớp ID. Đặt server ở `127.0.0.1` nên chương trình không cần kết nối Internet hoặc service ngoài. `ServerSocket(0, ...)` yêu cầu OS chọn cổng đang rảnh, tránh xung đột cổng cố định.

`setSoTimeout(3000)` làm một blocking read/accept thất bại nếu không có tiến triển theo timeout của socket. Nó **không phải deadline tổng cho toàn bộ frame**: peer có thể gửi từng ít byte ở nhiều lần đọc. Production cần time budget tổng, giới hạn socket và chính sách chống slow clients.

### 11.4. Record `Frame` và độ an toàn dữ liệu

`Frame` sao chép `payload` khi tạo và khi trả qua accessor để code bên ngoài không lặng lẽ sửa byte[] của frame. Tuy nhiên mỗi clone dùng thêm bộ nhớ; production có thể dùng immutable byte buffer/slice, zero-copy hoặc cơ chế cấp phát có giới hạn nếu cần tối ưu. Đó là quyết định hiệu năng riêng, không được ảnh hưởng hợp đồng wire.

## 12. Nếu chuyển sang NIO/Netty thì thuật toán có đổi không?

Không đổi hợp đồng frame; chỉ đổi cách gom byte.

Với `SocketChannel` và `ByteBuffer`:
- Một lần `channel.read(buffer)` có thể trả 0 hoặc ít hơn số byte cần. Ở non-blocking mode, 0 chỉ có nghĩa “hiện chưa có dữ liệu”; không phải EOF.
- Khi chưa đủ 16 byte header, giữ trạng thái `READ_HEADER` và các byte đã nhận trong buffer.
- Đủ header → parse và validate length → chuyển `READ_BODY`, tiếp tục tích lũy đúng N byte.
- Đủ body → dispatch một frame → chuyển `READ_HEADER` cho frame tiếp theo; nếu buffer còn byte, tiếp tục parse, vì có thể có **nhiều frame trong một lần đọc**.
- Khi ghi, `SocketChannel.write(ByteBuffer)` có thể ghi **ít hơn số byte còn lại**; phải tiếp tục cho tới khi buffer hết hoặc đăng ký sự kiện writable, tránh giả định một write gửi hết frame.

Netty có `LengthFieldBasedFrameDecoder` cho giao thức length-prefix, nhưng cấu hình phải khớp **offset=12, fieldLength=4, lengthAdjustment và initialBytesToStrip** theo định nghĩa cụ thể của protocol. Nếu length chỉ đếm payload và header dài 16 byte, cần tính chính xác total frame length. Dùng decoder có sẵn vẫn phải có **maxFrameLength**, kiểm tra version/type/flags và xử lý byte order.

Đối với hệ thống hiệu năng cao, một frame lớn có thể được xử lý streaming thay vì cấp phát hết vào một byte[]; nhưng streaming yêu cầu parser biết cách skip/drain chính xác khi request bị từ chối và không phá ranh giới frame tiếp theo.

## 13. Lỗi thiết kế độ dài và giới hạn tài nguyên

Một trường `payloadLength` rất tiện, nhưng cũng là điểm tấn công nếu tin người gửi:

1. **Đọc length trước khi validate:** nếu receiver thấy length `4_000_000_000` rồi cố tạo buffer, có thể overflow/mất bộ nhớ. Trong demo, 4 byte đọc vào signed `int`; giá trị âm hoặc > 1 MiB đều reject.
2. **Nhầm tổng độ dài và payload length:** sender ghi `16 + payload.length` nhưng receiver lại coi đó là số byte body → đọc lấn vào header frame tiếp theo rồi mất đồng bộ.
3. **Nhầm byte với số ký tự:** UTF-8 nhiều byte, như `Xin chào` có payload 9 byte. Không dùng `String.length()` làm length khi body đã mã hóa.
4. **Không giới hạn số frame đồng thời:** một frame tối đa 1 MiB vẫn có thể gây DoS nếu server cho hàng nghìn connection hoặc request đang chờ cùng lúc.
5. **Chỉ giới hạn chiều dài nén:** nếu sau này bật compression, còn cần giới hạn dữ liệu **sau giải nén**, tỷ lệ nén, CPU, thời gian và nesting.
6. **Không giới hạn tốc độ/tiến độ:** peer gửi 1 byte mỗi vài giây có thể chiếm slot quá lâu. Cần deadline toàn frame, idle timeout, quota và backpressure.
7. **Cấp phát theo length trước khi đọc/xác thực header:** phải xác minh magic, version, flags, type, length trước; payload format validation khi có đủ body.
8. **Không xử lý connection close giữa message:** nếu body chưa đủ, reject; không chuyển phần body còn lại sang request mới.

Chính sách nên định nghĩa rõ tối thiểu `MAX_PAYLOAD`, `MAX_CONNECTIONS`, số request chưa ACK, thời gian đọc 1 frame, kích thước hàng đợi và ngưỡng memory sử dụng. Các hạn mức ngoài length phụ thuộc loại dịch vụ, không có một số chung phù hợp mọi hệ thống.

## 14. Quản lý phiên kết nối, thứ tự và backpressure

### 14.1. Một connection có thể chứa nhiều frame

Nếu cùng một kết nối gửi liên tiếp:

```text
DATA(id=41,len=100) | DATA(id=42,len=250) | PING(id=0,len=0)
```

Decoder phải đọc:
1. Đúng 16 + 100 byte cho frame ID 41.
2. Đúng 16 + 250 byte cho frame ID 42.
3. Đúng 16 byte cho PING.
4. Sau đó mới đợi frame tiếp theo hoặc EOF.

Không tự `read` “cho tới khi socket đóng” để coi toàn bộ kết nối là một message, vì protocol cho phép **nhiều message trên một kết nối sống lâu**.

### 14.2. Pipelining, multiplexing và response trễ

TCP truyền byte có thứ tự; ứng dụng có thể xử lý DATA ID 42 nhanh hơn DATA ID 41 và gửi ACK theo thứ tự khác nếu protocol cho phép. Nếu protocol quy định response phải giữ đúng thứ tự thì cần enforce ở server. Nếu cho out-of-order response, client cần bảng `requestId → pending request` với timeout, cleanup và giới hạn số phần tử.

`requestId` giúp **correlate**, không thay cho:
- Transaction ID ở database.
- Idempotency key với phạm vi và TTL được bảo đảm.
- Authorization token hoặc session identity.
- TCP sequence number (nằm ở một tầng khác).

Nếu stream đóng sau khi client gửi DATA nhưng trước khi thấy ACK, client **không thể biết chắc** server đã commit hay chưa chỉ từ trạng thái TCP. Retry cần cơ chế idempotency/ack có ý nghĩa nghiệp vụ.

### 14.3. Slow reader và hàng đợi output

Nếu phía nhận xử lý chậm, TCP flow control sẽ làm sender chậm lại; nhưng ứng dụng vẫn có thể tự tích hàng triệu frame ở queue trước khi ghi. Cần:
- Giới hạn queue, số request in-flight và tổng byte đang chờ.
- Backpressure: tạm dừng đọc / từ chối request / báo overload theo hợp đồng.
- Không spawn thread mới vô hạn cho từng frame.
- Một đường ghi bảo đảm **header và body của từng frame không xen kẽ** với frame khác.
- Timeout và hủy request rõ ràng, giải phóng buffer khi disconnect.

Với Java blocking I/O, có thể dùng một worker theo connection có hạn mức hoặc pool; với NIO/Netty, quản lý state machine, event loop và watermarks. Cơ chế cụ thể khác nhau, wire contract vẫn giữ nguyên.

## 15. Lỗi giao thức: phản hồi ERROR hay đóng socket?

Không phải lỗi nào cũng nên gửi một frame ERROR.

| Tình huống | Xử lý đề xuất |
| --- | --- |
| DATA hợp lệ nhưng nghiệp vụ từ chối, parser vẫn đồng bộ | Có thể trả `ERROR` với requestId và mã lỗi được đặc tả |
| Magic sai hoặc version không hỗ trợ | Reject/đóng kết nối; không suy đoán diễn giải header |
| Flags/type không hỗ trợ | Theo chính sách v1.0: reject frame và đóng; trong revision khác có thể có negotiated optional type |
| Length âm/vượt giới hạn | Reject ngay, đóng socket; không cố đọc hết body không tin cậy |
| EOF giữa header/body | Frame truncated, bỏ dữ liệu không hoàn chỉnh và đóng |
| Timeout đọc giữa frame | Đóng hoặc hủy connection theo protocol; không dùng byte cũ làm frame mới |
| JSON/Protobuf payload sai schema nhưng header hợp lệ | Nếu đã đọc hết body và protocol cho phép thì trả `ERROR`; tuyệt đối không mất đồng bộ |

Khi trả ERROR phải tránh biến parser thành bộ phát dữ liệu lỗi không giới hạn, ví dụ trả về toàn bộ payload nhạy cảm mà client gửi. Mỗi ERROR nên có mã lỗi có thể máy xử lý, nội dung tối đa và quy tắc version. Đối với lỗi wire nặng, đóng connection rõ ràng thường đơn giản và an toàn hơn “tự khôi phục”.

**Tại sao không scan tìm magic?** Payload bất kỳ có thể chứa chuỗi `JMSG`. Sau khi parser mất vị trí, một lần match magic không đủ chứng minh đó là header thật. Resynchronization cần thiết kế riêng; giao thức mẫu không hỗ trợ.

## 16. Versioning, rolling upgrade và kiểm soát tương thích

Giả sử có ba phiên bản ứng dụng:
- **A:** hiểu header v1.0, DATA/ACK/PING cơ bản.
- **B:** muốn thêm một message type mới nhưng giữ bố cục 16 byte.
- **C:** muốn payload nén theo flags, thêm checksum hoặc tăng max frame.

Cần hỏi theo thứ tự:

1. **Peer cũ có nhận ra frame mới an toàn không?** Với code demo, unknown type hay flags khác 0 đều reject, nên B/C không thể tự bật tính năng mới khi còn client A.
2. **Có cần giữ endpoint v1.0?** Nếu phiên bản mới phá cú pháp hoặc semantics, duy trì bộ giải mã cũ ở endpoint riêng hoặc router theo version/handshake.
3. **Đặc tả “skip unknown” có hợp lệ không?** Chỉ khi length/schema và ý nghĩa optional được quy định; với type bắt buộc xử lý, skip sẽ mất nghiệp vụ.
4. **Có handshake chọn capability không?** Ví dụ phiên mới định nghĩa HELLO với danh sách (major,minor,features), bên nhận chọn giao nhau; nhưng handshake cũng phải có định dạng gốc mà hai bên nhận diện.
5. **Có thử nghiệm giao tiếp cả hai hướng không?** Old client ↔ new server, new client ↔ old server, downgrade, migration, rolling restart và rollback.
6. **Log có đầy đủ metadata để debug không?** Ghi version, type, requestId, length và mã lỗi (tránh log nguyên payload nhạy cảm).

Một hướng triển khai thực tế: trước tiên cập nhật server biết cả v1 và v2; sau đó mới phát hành client có khả năng thương lượng; cuối cùng bỏ v1 khi telemetry chứng minh không còn client phụ thuộc. **Không tự động tăng minor rồi cho rằng hai bên luôn tương thích.**

## 17. Kiểm thử wire protocol có tính quyết định

Bài demo đã kiểm:
- Đọc hai frame liên tiếp từ cùng một stream.
- Trả về cùng thông điệp khi bulk-read bị giới hạn 3 byte mỗi lần.
- Byte header chuẩn xác và length UTF-8 đúng 9.
- EOF sạch ở ranh giới giữa frame.
- Body thiếu byte → `EOFException`.
- Length vượt 1 MiB → reject trước cấp phát.
- TCP loopback client/server cùng process, DATA + PING và ACK cùng requestId.

Bộ kiểm thử production nên mở rộng:

| Case | Cách tạo | Kỳ vọng |
| --- | --- | --- |
| Header bị chia | Cho stream trả 1..15 byte trước, phần còn lại sau | Decoder chờ đủ header |
| Body bị chia | Gửi 1 byte mỗi lần tới đúng length | Decoder ghép đúng payload |
| Nhiều frame bị gộp | Đẩy tất cả byte của 100 frame vào một lần read | Giải mã đúng 100 frame theo thứ tự |
| Header thiếu | Cắt 1..15 byte đầu frame rồi EOF | Báo truncated header |
| Body thiếu | Header báo N, chỉ gửi N-1 rồi EOF | Báo truncated body |
| Magic sai | Sửa 1 byte tại offset 0..3 | Reject |
| Major/minor sai | Sửa offset 4/5 | Reject v1.0 |
| Type sai | Đặt byte offset 6 bằng 0 hoặc 255 | Reject |
| Flags chưa hỗ trợ | Offset 7 khác 0 | Reject |
| requestId sai | PING có ID khác 0, DATA có ID 0 | Reject |
| Length âm/uint32 rất lớn | Đặt 4 byte tại offset 12 thành `FF FF FF FF` | Reject trước allocation |
| Length sát ngưỡng | Thử 0, 1, 1_048_576, 1_048_577 | Nhận/từ chối đúng giới hạn |
| Payload UTF-8 | Dùng ASCII, dấu tiếng Việt, emoji | Length = số byte UTF-8 |
| Type không đúng schema | ACK có payload vô nghĩa | Lỗi schema theo contract |
| Parallel writes | Cho nhiều producer ghi cùng socket | Không xen byte giữa frames |
| Slowloris / slow send | Gửi từng byte chậm và dừng giữa frame | Deadline/timeout có giới hạn |
| Mất connection khi chờ ACK | Đóng socket sau khi server đọc DATA | Retry/idempotency theo contract |
| Old/new peers | Mỗi cặp version hỗ trợ và không hỗ trợ | Negotiation/reject đúng đặc tả |

Fuzzing các tổ hợp header 16 byte, length biên, UTF-8 sai, trạng thái chưa đủ byte và type lạ giúp phát hiện lỗi trước production. Đừng dừng ở happy path “gửi một lần, nhận một lần trên localhost”: loopback thường che giấu tình huống packet fragmentation/aggregation và backpressure.

## 18. Những sai lầm thường gặp

1. **“Một `write` là một message; một `read` cũng vậy.”** Sai: TCP chỉ bảo toàn dòng byte và thứ tự, không bảo toàn biên message do ứng dụng gọi.
2. **“`available() == 0` nghĩa là hết frame.”** Sai: `InputStream.available()` chỉ ước lượng byte có thể đọc mà không block; không dùng nó để xác định ranh giới hoặc EOF của protocol.
3. **“Dùng `read(byte[])` một lần là đủ lấy 16 byte header.”** Sai: read có thể trả ít hơn; dùng `readFully` hoặc state machine.
4. **“Length là `String.length()`.”** Sai: cần dùng số byte đã mã hóa UTF-8.
5. **“Trường length 4 byte nên cho phép tùy ý đến 4 GiB.”** Sai: tài nguyên thật cần hạn mức; không cấp phát theo giá trị không tin cậy.
6. **“Số nguyên trong Java tự xử lý unsigned.”** Sai: `byte` và `int` có dấu; phải định nghĩa diễn giải byte trên wire và validate giới hạn.
7. **“Đổi endian theo nền tảng chạy sẽ nhanh hơn.”** Sai: giao thức cần một thứ tự byte cố định để tương tác giữa các hệ thống.
8. **“Type mới luôn là thay đổi tương thích.”** Sai: client cũ có thể từ chối, parse sai hoặc thiếu xử lý bắt buộc; cần version/feature policy.
9. **“Minor lớn hơn luôn được phép.”** Sai với bản demo strict 1.0; chỉ cho phép khi đã đặc tả cơ chế tương thích và negotiation.
10. **“ACK của TCP nghĩa là server đã xử lý xong.”** Sai: đây là xác nhận tại tầng TCP; ACK ứng dụng phải có semantics được định nghĩa.
11. **“Magic đủ xác minh dữ liệu an toàn.”** Sai: magic không cung cấp authentication, confidentiality hoặc integrity.
12. **“Mỗi thread tự ghi một frame vào cùng socket là an toàn.”** Không chắc: các byte của các frame có thể bị xen kẽ; dùng one-writer queue hoặc synchronized write.
13. **“EOF lúc nào cũng là kết thúc message bình thường.”** Sai: EOF giữa header/body nghĩa là frame bị cắt.
14. **“Bắt IOException rồi tiếp tục đọc là ổn.”** Sai nếu parser đã lệch ranh giới; với lỗi wire nghiêm trọng, đóng connection và xử lý reconnect theo protocol.

## 19. Vận dụng: chọn hợp đồng trước khi code

**Tình huống A — Thiết bị IoT gửi số đo mỗi giây:** payload có thể chỉ vài byte; có thể chọn frame cố định hoặc length-prefixed tối giản. Dù vậy vẫn cần version/type/length hoặc quy tắc giới hạn rõ ràng, khả năng khôi phục khi mất kết nối và kiểm soát tốc độ.

**Tình huống B — RPC nội bộ có nhiều request đồng thời:** header nên có correlation ID và loại DATA/RESULT/ERROR. Cần timeout từng request, idempotency, xử lý response out-of-order và giới hạn in-flight. Nếu quy mô lớn, đánh giá gRPC/HTTP/2 trước khi tự tạo binary protocol.

**Tình huống C — Payload lớn hoặc streaming:** trường 32-bit length và buffer toàn bộ 1 MiB có thể không phù hợp. Xác định rõ chunk framing, stream ID, total size, checksum tùy mục đích và flow control, thay vì âm thầm nới MAX lên hàng trăm MiB.

**Tình huống D — Nâng cấp không downtime:** client cũ và mới chạy song song. Thiết kế negotiation/version policy rõ ràng, phép đo số client mỗi version và phương án downgrade/rollback; không gửi type mới đến peer chưa tuyên bố hỗ trợ.

Một bảng câu hỏi trước khi chốt giao thức:
- Ai sở hữu spec? Có tài liệu byte offsets, byte order, length semantics và vector test không?
- Mỗi type mang payload schema gì? Header/version có ảnh hưởng schema không?
- Cặp (major, minor) nào hỗ trợ, phiên bản lạ xử lý ra sao?
- Sender/receiver giới hạn kích thước, thời gian, số request/connection như thế nào?
- Có encryption/authentication, checksum ứng dụng, log và metrics gì?
- Lỗi giữa frame, timeout, reconnect, duplicate request và replay xử lý thế nào?
- Cần một connection dài hạn, nhiều connection hay streaming/chunking?

## 20. Bảo mật: framing chỉ là nền tảng

Header hợp lệ không chứng minh client đáng tin. Giao thức ứng dụng cần đặt các cơ chế khác đúng lớp:
- **TLS** cho bảo mật kênh và xác thực peer khi phù hợp, có cấu hình chứng chỉ tin cậy; không gửi credential nhạy cảm trên TCP plaintext chỉ vì đã có magic/version.
- **Authentication/authorization** cho từng kết nối hoặc request; requestId không phải token.
- **Integrity ứng dụng** nếu bài toán yêu cầu checksum/hash/chữ ký trên payload; checksum giúp nhận biết lỗi ngẫu nhiên nhưng không thay thế MAC/chữ ký bảo mật.
- **Quản lý tài nguyên**: max frame, total bytes, timeout, concurrency, backpressure, buffer pooling và quota.
- **Giới hạn parser** cho payload schema, kích thước sau giải nén, nested structures và input xấu.
- **Khả năng quan sát**: đếm rejected magic/version/type/length, truncated frame, thời gian xử lý, queue depth; tránh log raw payload có dữ liệu cá nhân/bí mật.

Không nên dùng header nhị phân tự thiết kế thay thế cho hệ thống bảo mật hoặc định nghĩa semantics của TCP.

## 21. Câu hỏi tự kiểm tra

**1. Client gọi `write(frame1)` và `write(frame2)` liên tiếp. Server có chắc nhận đúng hai lần `read` không?**  
Không. Server có thể nhận nhiều hoặc ít lần `read` tùy TCP/buffering. Framing dựa vào header+length mới xác định đúng từng frame.

**2. Header dài 16 byte, body `Xin chào` mã hóa UTF-8 dài 9 byte. Phải ghi length bao nhiêu?**  
Ghi `9` vì trường định nghĩa số byte body, không bao gồm header và không dùng số ký tự.

**3. Header báo payloadLength = 2_000_000 trong khi MAX_PAYLOAD = 1_048_576. Decoder cần làm gì?**  
Từ chối trước khi cấp phát/đọc body, sau đó xử lý protocol error và đóng kết nối theo hợp đồng v1.0.

**4. Bản v1.0 nhận `major=1, minor=1` có thể tự bỏ qua minor không?**  
Không: demo chỉ hiểu 1.0 và chưa có negotiation/cơ chế mở rộng, nên reject. Bản sau chỉ được chấp nhận minor mới theo spec tương thích cụ thể.

**5. PING với ID 0 và body rỗng có size wire bao nhiêu?**  
`16` byte: đúng một header, không có byte payload.

**6. Server trả ACK ID 42 nhưng client đang đợi ID 43. Có thể coi là xong request 43 không?**  
Không. Correlation ID phải được so khớp với request đang chờ; ACK TCP cũng không thay thế ACK nghiệp vụ.

**7. Vì sao thiếu 1 byte payload rồi EOF lại khác EOF khi chưa thấy header tiếp theo?**  
Thiếu byte payload là frame chưa hoàn chỉnh; EOF ở ranh giới giữa frames mới có thể coi là stream kết thúc sạch.

**8. Nếu muốn thêm compression theo flags mà không phá client cũ, cần gì?**  
Cần đặc tả chính xác bit/thuật toán, giới hạn sau giải nén và negotiation/capability hoặc version mới. Client cũ v1.0 từ chối flags khác 0.

## 22. Tài liệu tham khảo

- RFC 9293 — Transmission Control Protocol, `3.7 Segmentation: https://www.rfc-editor.org/rfc/rfc9293
- Java SE 17 `DataInputStream` / `readFully` / `EOFException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html
- Java SE 17 `DataOutputStream` và byte order trong `writeInt`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- Java SE 17 `ByteBuffer` và `ByteOrder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `Socket` / `ServerSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17 `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels: https://www.rfc-editor.org/rfc/rfc2119
