# Dữ liệu logic và biểu diễn vật lý bằng byte

Một ứng dụng Java có thể làm việc với một đơn hàng có mã `42`, số lượng `3`, số tiền `125000.50` và tên hàng `"Cà phê"`. Đối với lập trình viên, đây là **các giá trị mang ý nghĩa nghiệp vụ**. Nhưng khi truyền qua mạng hoặc lưu vào tệp, hệ thống phải chuyển những giá trị đó thành **dãy byte**. Cơ sở dữ liệu cũng phải tổ chức thông tin lên các phương tiện lưu trữ theo một biểu diễn vật lý nhất định.

Hai cách nhìn này trả lời hai câu hỏi khác nhau:

- **Dữ liệu logic là gì?** Giá trị nào đang được biểu diễn, thuộc kiểu gì, có ý nghĩa và ràng buộc nào?
- **Biểu diễn vật lý bằng byte là gì?** Giá trị ấy được mã hóa thành những byte nào, được phân định ranh giới ra sao và được diễn giải lại bằng quy tắc nào?

Bài học thuộc chương **Biểu diễn dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Nắm được sự khác biệt này giúp người học thiết kế mô hình dữ liệu và lược đồ, hiểu các lựa chọn truy vấn và chỉ mục, xử lý serialization, thiết kế ranh giới persistence trong Java, đồng thời chuẩn bị cho những chủ đề về giao dịch, kiểm soát đồng thời, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Cùng một dữ liệu có nhiều lớp biểu diễn

Xét một sản phẩm:

~~~text
Mã sản phẩm: 42
Tên:         Cà phê
Số lượng:    3
Đơn giá:     125000.50 VND
~~~

Ở tầng nghiệp vụ, hệ thống có thể mô tả sản phẩm qua một cấu trúc:

~~~java
import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

Một phiên bản trao đổi qua API có thể là JSON:

~~~json
{
  "id": 42,
  "name": "Cà phê",
  "quantity": 3,
  "unitPrice": "125000.50"
}
~~~

JSON là văn bản có thể mã hóa bằng UTF-8 thành byte để gửi qua mạng hoặc ghi vào tệp. Việc đặt `unitPrice` dưới dạng chuỗi là **một quyết định của hợp đồng API** nhằm tránh một số vấn đề về số thập phân khi phía nhận sử dụng số dấu phẩy động; các hệ thống khác có thể dùng JSON number kèm quy tắc xử lý thập phân chính xác.

Trong cơ sở dữ liệu quan hệ, ta có thể khai báo:

~~~sql
CREATE TABLE products (
    id         BIGINT PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price DECIMAL(19, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Ba hình thức trên có thể cùng biểu diễn **một sản phẩm về mặt logic**, nhưng **không cùng cách bố trí byte**. Java lưu đối tượng theo cơ chế runtime, JSON dùng văn bản, còn bộ máy database quyết định cách biểu diễn hàng, cột, chỉ mục, trang và nhật ký trên đĩa.

~~~mermaid
flowchart TD
    A["Ý nghĩa nghiệp vụ: sản phẩm 42"] --> B["Mô hình logic: ID, tên, số lượng, đơn giá"]
    B --> C["Đối tượng Java"]
    B --> D["Hàng trong bảng SQL"]
    B --> E["JSON / định dạng truyền dữ liệu"]
    C --> F["Biểu diễn nội bộ của JVM"]
    D --> G["Trang dữ liệu, chỉ mục và log do DB quản lý"]
    E --> H["Byte UTF-8 hoặc định dạng nhị phân"]
    F --> I["Bộ nhớ máy tính"]
    G --> J["Tệp / thiết bị lưu trữ"]
    H --> K["Mạng hoặc thiết bị lưu trữ"]
~~~

Lược đồ logic không quyết định một cách duy nhất biểu diễn vật lý. Hai hệ quản trị có thể cho cùng kết quả của câu `SELECT` nhưng có định dạng trang, chỉ mục và write-ahead log hoàn toàn khác nhau.

## 2. Dữ liệu logic: giá trị, kiểu, quan hệ và bất biến

**Dữ liệu logic (logical data)** là cách mô tả dữ liệu theo những giá trị và quy tắc có ý nghĩa đối với ứng dụng, không phụ thuộc trực tiếp vào vị trí byte trong RAM hay trên đĩa.

Với đối tượng `Product`, các yếu tố logic gồm:

| Thành phần | Ý nghĩa logic | Ví dụ |
| --- | --- | --- |
| Định danh | Phân biệt các sản phẩm | `id = 42` |
| Văn bản | Tên có thể hiển thị cho người dùng | `name = "Cà phê"` |
| Số nguyên | Số lượng đơn vị | `quantity = 3` |
| Số thập phân | Số tiền yêu cầu độ chính xác thập phân | `unitPrice = 125000.50` |
| Ràng buộc | Giá trị hợp lệ trong nghiệp vụ | Số lượng và đơn giá không âm |
| Quan hệ | Liên kết với đơn hàng, danh mục, tồn kho | Mã sản phẩm được tham chiếu từ dòng đơn hàng |

Một giá trị không thể được hiểu đầy đủ chỉ dựa vào byte của nó. Dãy byte `00 00 00 2A` có thể mang nghĩa số nguyên **42** khi đọc theo kiểu số nguyên 32-bit big-endian, hoặc có thể là bốn byte nhị phân của một mã định danh, một phần ảnh hay dữ liệu nén.

**Kiểu và lược đồ cung cấp ngữ cảnh để diễn giải byte.** Cần biết ít nhất cách mã hóa, độ dài, thứ tự byte, quy tắc nhận diện các trường và phiên bản định dạng.

Cũng cần phân biệt:

- **Mô hình nghiệp vụ (domain model):** đối tượng và quy tắc như “số lượng bán không vượt tồn kho”.
- **Mô hình dữ liệu logic:** cấu trúc, các kiểu trường, khóa, quan hệ và ràng buộc.
- **Biểu diễn vật lý:** byte, thứ tự, trang, bản ghi lưu trữ và cơ chế truy xuất.

Một ràng buộc logic có thể được áp dụng ở nhiều tầng: Java validation, kiểm tra nghiệp vụ và database `CHECK` hoặc khóa ngoại. Việc chọn cách lưu byte không tự bảo đảm ràng buộc đó luôn đúng.

## 3. Byte là gì và vì sao phải có quy tắc giải mã?

**Byte** là đơn vị thông tin gồm **8 bit** trong hầu hết hệ thống tính toán hiện đại; một byte có 256 mẫu bit có thể có, từ `00000000` đến `11111111`. Các mẫu này thường được viết gọn bằng **hexadecimal (hệ 16)**:

~~~text
Nhị phân:  0010 1010
Hex:       2A
Thập phân: 42 (nếu diễn giải là số nguyên không dấu 8-bit)
~~~

Bản thân byte **không mang nhãn “đây là tên”, “đây là giá tiền” hay “đây là timestamp”**. Chương trình cần quy ước để đọc dữ liệu.

Ví dụ:

~~~text
Byte: 34 32
Giải mã ASCII/UTF-8: chuỗi "42"
Giải mã như số nguyên 16-bit big-endian: số 13362
~~~

Hai byte `34 32` trong hex là ký tự `'4'` và `'2'` khi đọc bằng ASCII/UTF-8. Nhưng khi ghép như một số nguyên không dấu 16-bit big-endian, chúng biểu diễn `0x3432 = 13362`. Ý nghĩa phụ thuộc **hợp đồng giải mã**, không phụ thuộc việc byte đã được lưu ở đâu.

### Bit, byte và định dạng tệp

Một tệp chỉ là một chuỗi byte từ góc nhìn của chương trình đọc. Phần đuôi `.json`, `.png` hay `.bin` gợi ý định dạng nhưng không đảm bảo nội dung hợp lệ. Để đọc chính xác, cần:

1. Biết hoặc phát hiện **định dạng**.
2. Biết **phiên bản định dạng**.
3. Xác định **độ dài và ranh giới trường**.
4. Giải mã theo **charset/endianness/kiểu dữ liệu**.
5. Kiểm tra **tính toàn vẹn và ràng buộc** trước khi đưa vào xử lý nghiệp vụ.

Một số định dạng có **magic bytes** ở đầu để nhận diện loại tệp; định dạng khác sử dụng metadata ở bên ngoài. Không có một bố cục chung áp dụng cho mọi hệ lưu trữ.

## 4. Số nguyên: cùng giá trị, nhiều cách mã hóa byte

Giá trị logic **42** có thể được biểu diễn bằng nhiều định dạng:

| Kiểu biểu diễn | Byte minh họa | Dung lượng | Lưu ý |
| --- | --- | ---: | --- |
| Văn bản ASCII/UTF-8 `"42"` | `34 32` | 2 byte | Hai ký tự chữ số |
| Số nguyên 8-bit không dấu | `2A` | 1 byte | Miền giá trị 0–255 |
| Số nguyên 32-bit big-endian | `00 00 00 2A` | 4 byte | Byte trọng số lớn trước |
| Số nguyên 32-bit little-endian | `2A 00 00 00` | 4 byte | Byte trọng số nhỏ trước |
| Số nguyên 64-bit big-endian | `00 00 00 00 00 00 00 2A` | 8 byte | Độ rộng lớn hơn |

Trong Java, `byte` là kiểu **số nguyên 8-bit có dấu** (miền `-128` đến `127`). `int` thường được hiểu ở mức ngôn ngữ là **số nguyên 32-bit có dấu**, còn `long` là **64-bit có dấu**. Quy tắc mã hóa ra một dãy byte bên ngoài JVM phải được chỉ rõ, thay vì suy từ việc khai báo `int`.

### Endianness: thứ tự byte

Với số nguyên `0x01020304`:

~~~text
Big-endian:     01 02 03 04
Little-endian:  04 03 02 01
~~~

Ở big-endian, byte có trọng số cao đứng trước; little-endian đặt byte có trọng số thấp trước. Nếu một bên ghi little-endian và bên nhận đọc big-endian, giá trị giải mã sẽ khác.

Java `ByteBuffer` cho phép kiểm soát rõ thứ tự:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

int value = 0x01020304;

byte[] big = ByteBuffer.allocate(Integer.BYTES)
    .order(ByteOrder.BIG_ENDIAN)
    .putInt(value)
    .array();

byte[] little = ByteBuffer.allocate(Integer.BYTES)
    .order(ByteOrder.LITTLE_ENDIAN)
    .putInt(value)
    .array();

System.out.println(HexFormat.of().formatHex(big));    // 01020304
System.out.println(HexFormat.of().formatHex(little)); // 04030201

int restored = ByteBuffer.wrap(big)
    .order(ByteOrder.BIG_ENDIAN)
    .getInt();

System.out.println(restored == value); // true
~~~

`ByteBuffer` mặc định dùng big-endian, nhưng khai báo tường minh giúp người đọc biết hợp đồng và tránh sai sót khi tích hợp với hệ thống khác.

### Số âm và overflow

Số nguyên có dấu Java sử dụng **biểu diễn bù hai (two's complement)**. Trong biểu diễn 32-bit, `-1` có các bit `11111111` lặp bốn byte, thường viết hex là `FF FF FF FF`. Nếu đọc cùng byte đó như số 32-bit không dấu, kết quả là `4.294.967.295`. Đây là một ví dụ khác cho thấy **cùng byte, khác kiểu và ý nghĩa**.

Khi chọn kiểu số, cần kiểm soát:

- Miền giá trị và khả năng overflow khi tính toán.
- Signed/unsigned khi kết nối định dạng nhị phân không thuộc Java.
- Độ rộng và thứ tự byte.
- Quy tắc biểu diễn giá trị không tồn tại hoặc không hợp lệ.

Không tự sử dụng giá trị đặc biệt như `-1` để chỉ `NULL` nếu hợp đồng dữ liệu chưa quy định rõ, vì `-1` có thể là dữ liệu hợp lệ của một miền khác.

## 5. Số thập phân: đừng nhầm giá trị tiền với dấu phẩy động nhị phân

Nhiều nghiệp vụ yêu cầu các số thập phân **chính xác**, chẳng hạn tiền, thuế, đơn giá hoặc khối lượng được định lượng. Các kiểu `float` và `double` dùng IEEE 754 dạng dấu phẩy động nhị phân trong Java; nhiều số thập phân như `0.1` không thể được biểu diễn chính xác hữu hạn ở dạng nhị phân này.

~~~java
System.out.println(0.1 + 0.2); // 0.30000000000000004
~~~

Với tiền, nên cân nhắc:

- **`BigDecimal` trong Java**, được tạo từ chuỗi thập phân hoặc phương thức phù hợp; không dùng `new BigDecimal(0.1)` nếu muốn biểu diễn chính xác giá trị thập phân 0.1.
- **`DECIMAL(p, s)` / `NUMERIC` trong SQL** để diễn đạt số thập phân có độ chính xác và scale được quản lý.
- **Số nguyên đơn vị nhỏ nhất** (ví dụ đơn vị đồng hoặc xu) nếu đơn vị, phạm vi và các phép tính được xác định rõ.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("125000.50");
BigDecimal quantity = new BigDecimal("3");

BigDecimal total = price.multiply(quantity)
    .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(total.toPlainString()); // 375001.50
~~~

Nếu tự thiết kế định dạng nhị phân, có thể biểu diễn giá trị dưới dạng **unscaled integer + scale**. Chẳng hạn:

~~~text
Giá trị logic: 125000.50
Unscaled value: 12500050
Scale: 2
Giải mã: 12500050 × 10^(-2) = 125000.50
~~~

Đó chỉ là **một quy ước**; cách database lưu `DECIMAL` vật lý có thể khác và không nên đoán từ cách Java lưu `BigDecimal`. Cũng cần chỉ rõ quy tắc làm tròn, đơn vị tiền tệ và cách xử lý tràn miền giá trị.

## 6. Chuỗi ký tự: Unicode, charset và số byte

Chuỗi logic `"Cà phê"` là các ký tự Unicode. Để lưu/truyền, ta phải chọn một **character encoding** như UTF-8.

UTF-8 biểu diễn mỗi Unicode code point bằng 1–4 byte. Vì thế, **số ký tự không nhất thiết bằng số byte**. Ví dụ:

| Giá trị logic | Các byte UTF-8 (hex) | Dung lượng |
| --- | --- | ---: |
| `"A"` | `41` | 1 byte |
| `"é"` (U+00E9) | `C3 A9` | 2 byte |
| `"ắ"` (U+1EAF) | `E1 BA AF` | 3 byte |
| `"😀"` (U+1F600) | `F0 9F 98 80` | 4 byte |

Trong Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String value = "Cà phê";
byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

System.out.println(utf8.length);                      // Số byte UTF-8
System.out.println(HexFormat.of().formatHex(utf8));  // Dữ liệu nhị phân dạng hex

String restored = new String(utf8, StandardCharsets.UTF_8);
System.out.println(restored.equals(value));          // true
~~~

Java `String.length()` đếm **đơn vị mã UTF-16**, không phải số code point Unicode và cũng không phải số byte UTF-8. Ví dụ emoji `"😀"` thường chiếm **2 đơn vị mã UTF-16**, **1 code point** và **4 byte UTF-8**.

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4 bytes
~~~

### Unicode normalization: nhìn giống nhau chưa chắc byte giống nhau

Chữ **é** có thể biểu diễn bằng một code point U+00E9 hoặc bằng chữ `e` U+0065 kết hợp dấu sắc U+0301. Chúng có thể hiển thị giống nhau nhưng khác chuỗi code point và khác byte UTF-8.

~~~java
import java.text.Normalizer;

String composed = "\u00E9";       // U+00E9
String decomposed = "e\u0301";    // U+0065 + U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(
    Normalizer.normalize(decomposed, Normalizer.Form.NFC)
        .equals(composed)
); // true
~~~

Điều này quan trọng khi so sánh chuỗi, tạo khóa, tính hash, kiểm tra trùng lặp hoặc tạo chữ ký số. Việc database so sánh chuỗi thế nào còn phụ thuộc **collation** và cấu hình; không mặc định mọi database coi hai cách mã hóa là bằng nhau.

### Lỗi mã hóa và bảo mật

Nếu một phía dùng UTF-8 còn phía nhận đoán một charset khác, tên tiếng Việt có thể bị lỗi ký tự (*mojibake*). Với dữ liệu không tin cậy, cần xác định chính sách xử lý chuỗi byte không hợp lệ: báo lỗi hay thay ký tự. Dữ liệu nhị phân tùy ý **không nên được chuyển sang `String` bằng charset mặc định** rồi kỳ vọng luôn phục hồi nguyên vẹn.

Nếu cần biểu diễn byte tùy ý bằng văn bản, có thể dùng **hex** hoặc **Base64** theo hợp đồng đã xác định; Base64 là **mã hóa biểu diễn**, không phải nén hoặc mã hóa bảo mật.

## 7. Ranh giới trường: đọc bao nhiêu byte là một giá trị?

Giả sử có các byte biểu diễn:

~~~text
Product(id=42, name="Cà phê", quantity=3)
~~~

Nếu ghi nối liền `id`, `name` và `quantity`, bên nhận phải biết:

- `id` dài bao nhiêu byte?
- `name` dài bao nhiêu byte?
- Có trường nào được phép vắng mặt hoặc `NULL`?
- Trường nào trước, trường nào sau?
- Định dạng có thay đổi giữa phiên bản cũ và mới không?

Các cách phân tách thường gặp:

| Cách | Ví dụ | Ưu điểm / giới hạn |
| --- | --- | --- |
| **Độ dài cố định** | `id` luôn 8 byte | Đọc nhanh, nhưng không hợp chuỗi có độ dài thay đổi |
| **Length prefix** | Số byte chuỗi + byte UTF-8 của chuỗi | Biết chính xác ranh giới; phải chặn length âm/quá lớn |
| **Delimiter** | Dấu xuống dòng giữa các bản ghi văn bản | Dễ đọc; cần escaping nếu dữ liệu có delimiter |
| **Tag–length–value** | Mã trường + độ dài + nội dung | Cho phép thêm trường linh hoạt nếu thiết kế tốt |
| **Schema bên ngoài** | Avro/Protobuf theo schema | Có cấu trúc và quy tắc phiên bản; cần phối hợp schema |
| **Cấu trúc tệp chuẩn** | JSON, CSV, XML, Parquet | Quy tắc và công cụ có sẵn; vẫn cần kiểm soát encoding/kiểu |

Đối với định dạng tự xây, tối thiểu cần công bố **endianness, độ rộng trường, charset, cách biểu diễn NULL, giới hạn kích thước, phiên bản và quy tắc mở rộng**. Thiếu một trong những điều này có thể khiến dữ liệu ghi hôm nay không đọc được về sau.

## 8. Ví dụ Java: mã hóa một bản ghi logic thành dãy byte có phiên bản

Ta thiết kế một **định dạng minh họa** cho bản ghi tồn kho:

~~~text
ProductStock(id: long, quantity: int, name: String)
~~~

Bố cục byte được chọn, theo thứ tự:

| Trường | Độ dài | Diễn giải |
| --- | ---: | --- |
| Magic `DPF1` | 4 byte | Nhận diện loại dữ liệu |
| Format version | 2 byte | Số nguyên 16-bit big-endian, hiện là `1` |
| ID | 8 byte | Số nguyên 64-bit big-endian |
| Quantity | 4 byte | Số nguyên 32-bit big-endian |
| Name length | 4 byte | Số byte UTF-8 của tên, không phải số ký tự |
| Name bytes | `name length` byte | Chuỗi tên mã hóa UTF-8 |

Đây là **định dạng ứng dụng tự định nghĩa** để minh họa; không phải bố cục lưu trữ của PostgreSQL, MySQL hay Java serialization mặc định.

Một lớp Java sử dụng các API có sẵn trong JDK:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class StockCodec {
    private static final int MAGIC = 0x44504631; // ASCII "DPF1"
    private static final short VERSION = 1;
    private static final int MAX_NAME_BYTES = 1024;
    private static final int HEADER_BYTES =
        Integer.BYTES + Short.BYTES + Long.BYTES
        + Integer.BYTES + Integer.BYTES;

    public record ProductStock(long id, int quantity, String name) {}

    public static byte[] encode(ProductStock stock) {
        if (stock == null || stock.name() == null
                || stock.quantity() < 0) {
            throw new IllegalArgumentException("Bản ghi không hợp lệ");
        }

        byte[] nameBytes =
            stock.name().getBytes(StandardCharsets.UTF_8);

        if (nameBytes.length > MAX_NAME_BYTES) {
            throw new IllegalArgumentException("Tên quá dài");
        }

        ByteBuffer buffer = ByteBuffer
            .allocate(HEADER_BYTES + nameBytes.length)
            .order(ByteOrder.BIG_ENDIAN);

        buffer.putInt(MAGIC);
        buffer.putShort(VERSION);
        buffer.putLong(stock.id());
        buffer.putInt(stock.quantity());
        buffer.putInt(nameBytes.length);
        buffer.put(nameBytes);

        return buffer.array();
    }

    public static ProductStock decode(byte[] data)
            throws CharacterCodingException {
        if (data == null || data.length < HEADER_BYTES) {
            throw new IllegalArgumentException("Thiếu header");
        }

        ByteBuffer buffer = ByteBuffer.wrap(data)
            .order(ByteOrder.BIG_ENDIAN);

        if (buffer.getInt() != MAGIC) {
            throw new IllegalArgumentException("Sai magic");
        }

        if (buffer.getShort() != VERSION) {
            throw new IllegalArgumentException("Version không hỗ trợ");
        }

        long id = buffer.getLong();
        int quantity = buffer.getInt();
        int nameLength = buffer.getInt();

        if (quantity < 0 || nameLength < 0
                || nameLength > MAX_NAME_BYTES
                || nameLength != buffer.remaining()) {
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        }

        byte[] nameBytes = new byte[nameLength];
        buffer.get(nameBytes);

        String name = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(nameBytes))
            .toString();

        return new ProductStock(id, quantity, name);
    }
}
~~~

Gọi thử:

~~~java
StockCodec.ProductStock original =
    new StockCodec.ProductStock(42L, 3, "Cà phê");

byte[] encoded = StockCodec.encode(original);
StockCodec.ProductStock restored = StockCodec.decode(encoded);

System.out.println(original.equals(restored)); // true
System.out.println(encoded.length); // Header + độ dài UTF-8 của tên
~~~

**Đọc ví dụ đúng phạm vi:**

1. `encode()` tạo **byte trong RAM**. Chưa có hoạt động persistence cho đến khi byte được ghi vào nơi lưu trữ thích hợp.
2. `decode()` đọc và kiểm tra bố cục, version, độ dài và UTF-8 lỗi. Nhưng còn cần xác thực quy tắc nghiệp vụ chuyên sâu và chính sách bảo mật.
3. Có giới hạn `MAX_NAME_BYTES` để tránh một số trường hợp cấp phát quá lớn từ input. Hệ thống thực cần giới hạn cả tổng dung lượng thông điệp và tài nguyên xử lý.
4. Định dạng chưa có **checksum**, **chữ ký**, **mã hóa**, **schema evolution** hoặc kiểm tra toàn vẹn dữ liệu dài hạn. Không nên coi ví dụ là giao thức production hoàn chỉnh.
5. `getBytes(StandardCharsets.UTF_8)` sẽ xử lý chuỗi Java chứa surrogate không hợp lệ theo chính sách của encoder mặc định; nếu cần chặn dữ liệu văn bản không hợp lệ một cách chặt chẽ, hãy dùng `CharsetEncoder` với `CodingErrorAction.REPORT` khi mã hóa.

### Từ byte trong RAM đến persistence

Giả sử muốn lưu bản ghi đã mã hóa vào một tệp:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of("stock-42.bin");
byte[] encoded = StockCodec.encode(original);

Files.write(
    file,
    encoded,
    StandardOpenOption.CREATE_NEW
);

byte[] readBack = Files.readAllBytes(file);
StockCodec.ProductStock restored = StockCodec.decode(readBack);
~~~

`CREATE_NEW` thất bại nếu file đã tồn tại. Đọc lại kiểm tra tính tương thích giữa dữ liệu ghi và codec, nhưng **chưa chứng minh mức độ bền vững trước mất điện**, cũng chưa có cơ chế thay thế nguyên tử, khóa file, sao lưu hoặc phục hồi. Với các bản ghi nghiệp vụ quan trọng, các yêu cầu durability và đồng thời phải được thiết kế riêng.

Tương tự, có thể lưu dãy byte này vào cột kiểu nhị phân như `BYTEA` hoặc `VARBINARY` tùy database, nhưng lúc đó database chỉ biết đó là **payload nhị phân** trừ khi ứng dụng xây dựng thêm metadata/schema và cách truy vấn. Các trường `quantity` hay `name` nằm bên trong blob sẽ khó được lọc, đánh index hoặc ràng buộc như các cột có kiểu riêng.

## 9. NULL, trường tùy chọn và dữ liệu thiếu

**Giá trị `NULL`** trong SQL thể hiện thiếu/không biết giá trị theo mô hình SQL. Nó không đồng nhất với:

- Số `0`.
- Chuỗi rỗng `""`.
- Byte `00`.
- Trường chưa có trong một phiên bản schema.
- Tham chiếu `null` của Java trong mọi ngữ cảnh.

Nếu tự tạo định dạng byte, phải quyết định cách thể hiện tính tùy chọn. Ví dụ có thể dùng:

~~~text
hasDescription: 1 byte (00 = không có, 01 = có)
descriptionLength: 4 byte (chỉ xuất hiện nếu hasDescription = 01)
description: N byte UTF-8
~~~

Một định dạng khác dùng `length = -1` để phân biệt `NULL` và độ dài `0` cho chuỗi rỗng. Cả hai là lựa chọn hợp lệ **nếu được ghi rõ trong hợp đồng** và parser kiểm tra chúng.

Khi đưa dữ liệu từ Java vào SQL, không nên tự quy ước mọi giá trị `null` thành chuỗi rỗng. Dùng phương thức JDBC và kiểu cột phù hợp, ví dụ `PreparedStatement.setNull(index, Types.VARCHAR)` khi cần truyền SQL NULL.

## 10. Tầng dữ liệu logic không đồng nhất với cách database lưu byte

Trong database quan hệ, ứng dụng thao tác trên **bảng, cột, hàng, khóa và kiểu SQL**. Còn hệ quản trị xử lý nhiều cấu trúc vật lý bên dưới, tùy triển khai:

| Khái niệm logic | Một số cơ chế vật lý có thể liên quan |
| --- | --- |
| Hàng dữ liệu | Record/tuple đặt trong trang lưu trữ; có header và metadata |
| Cột `INTEGER` / `DECIMAL` | Mã hóa riêng của hệ quản trị cho kiểu tương ứng |
| Giá trị văn bản | Charset/encoding, độ dài, collation, metadata tùy hệ |
| Khóa chính hoặc chỉ mục | B-tree, hash hoặc cấu trúc index khác theo engine |
| Giao dịch đã ghi | Transaction log, WAL/redo, checkpoint, flush |
| Truy cập đồng thời | Lock, phiên bản MVCC hoặc cơ chế kiểm soát khác |

Ví dụ câu lệnh:

~~~sql
SELECT id, name, quantity
FROM products
WHERE id = 42;
~~~

Ứng dụng nhận các giá trị theo kiểu dữ liệu và API truy xuất. Nó **không cần** và cũng **không nên** giả định rằng giá trị số `42` trong file nội bộ database được lưu chính xác bằng bốn byte `00 00 00 2A`.

Hệ quản trị có thể sử dụng định dạng lưu trữ riêng, cấu trúc trang, các phiên bản bản ghi và tối ưu hóa như nén. Cấu trúc vật lý có thể thay đổi theo phiên bản engine, loại dữ liệu hoặc cấu hình. Các tệp dữ liệu nội bộ không phải giao thức trao đổi di động để ứng dụng tự giải mã.

### Bố cục logic và thứ tự vật lý

Không có bảo đảm rằng các hàng được lưu trên đĩa đúng thứ tự của `INSERT` hoặc thứ tự khóa chính. Muốn nhận kết quả sắp xếp, truy vấn phải chỉ định `ORDER BY`.

~~~sql
SELECT id, name
FROM products
ORDER BY id;
~~~

Chỉ mục có thể cải thiện truy xuất theo điều kiện phù hợp, nhưng không tự làm dữ liệu trả về có thứ tự khi truy vấn không yêu cầu. Bố trí byte và index thực tế là quyết định của engine và query planner.

## 11. Serialization, object mapping và persistence nằm ở đâu?

Ba khái niệm thường xuất hiện liền nhau nhưng giữ trách nhiệm riêng:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Object mapping** | Chuyển giữa các mô hình có cấu trúc khác nhau thế nào? | `ProductEntity` → `ProductResponse` |
| **Serialization** | Chuyển giá trị thành biểu diễn truyền/lưu được thế nào? | `ProductResponse` → JSON UTF-8 hoặc protobuf bytes |
| **Persistence** | Lưu và khôi phục dữ liệu qua vòng đời tiến trình theo yêu cầu thế nào? | Ghi hàng SQL, ghi tệp hoặc gửi dữ liệu đến kho lưu bền |

Một Java `record` có các trường logic; bộ serializer quyết định byte của JSON hoặc định dạng nhị phân; tầng repository/DAO quyết định các thao tác trên kho dữ liệu; database quyết định format vật lý của bảng và log. **Chuyển đối tượng thành byte chưa có nghĩa là byte đã được lưu bền vững**.

Ví dụ dùng Jackson để tạo JSON UTF-8:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;

ObjectMapper mapper = new ObjectMapper();

Product product = new Product(
    42L,
    "Cà phê",
    3,
    new BigDecimal("125000.50")
);

byte[] bytes = mapper.writeValueAsBytes(product);
String json = new String(bytes, StandardCharsets.UTF_8);
~~~

Đoạn mã giả định có Jackson và kiểu `Product` ở đầu bài. Kết quả `bytes` vẫn tồn tại trong bộ nhớ. Nếu đưa byte qua HTTP, ghi vào file hay lưu thành blob, cần một bước I/O tiếp theo; nếu muốn kiểm soát transaction cần một hợp đồng riêng.

## 12. Tiến hóa schema và khả năng đọc dữ liệu cũ

Định dạng lưu dài hạn thường sống lâu hơn một phiên bản ứng dụng. Ví dụ phiên bản 1 có `id`, `quantity`, `name`; phiên bản 2 thêm `category` hoặc đổi tên trường. Nếu reader của v1 chỉ biết độ dài cố định mà v2 chèn thêm byte vào giữa, dữ liệu cũ hoặc mới có thể bị đọc sai.

Những chiến lược cơ bản:

1. **Gắn version vào định dạng.** Khi decode, chọn quy tắc tương ứng hoặc báo lỗi rõ ràng nếu version chưa hỗ trợ.
2. **Thiết kế khả năng bỏ qua trường không biết.** Dùng tag–length–value hoặc định dạng có quy tắc backward/forward compatibility nếu nhu cầu phù hợp.
3. **Giữ quy tắc mã hóa ổn định.** Charset, endianness, độ rộng, đơn vị, scale và cách diễn giải thời gian cần được công bố.
4. **Đặt chính sách mặc định cho trường mới.** Dữ liệu cũ không có trường `category` có thể phải nhận giá trị mặc định hoặc cần migration; không được suy đoán tùy ý.
5. **Thử đọc dữ liệu cũ bằng code mới.** Có bộ mẫu byte đại diện từng version và kiểm tra round-trip khi cần.
6. **Quản lý schema database độc lập với API.** Thay một cột SQL không nhất thiết bắt buộc thay JSON; cần mapping/migration rõ ràng ở ranh giới.

### Thời gian cũng cần ngữ nghĩa, không chỉ byte

Một giá trị `1700000000` có thể là epoch seconds, epoch milliseconds, số ngày, mã phiên hoặc một số nguyên bình thường. Không có metadata thì không thể suy ra ý nghĩa.

Trong Java, một mốc thời gian tuyệt đối có thể được biểu diễn bằng `Instant`. Khi truyền/lưu dạng epoch, cần quy định **đơn vị** (`seconds`, `milliseconds`, `microseconds`), **gốc thời gian**, **miền giá trị**, và cách xử lý múi giờ khi hiển thị.

~~~java
import java.time.Instant;

Instant createdAt = Instant.parse("2025-01-02T03:04:05Z");
long epochMillis = createdAt.toEpochMilli();

Instant restored = Instant.ofEpochMilli(epochMillis);
System.out.println(restored.equals(createdAt)); // true
~~~

Ví dụ có độ chính xác tới mili giây nên round-trip theo millisecond không mất phần nano. Với một `Instant` có nano giây không chia hết cho mili giây, chuyển sang `epochMillis` sẽ mất độ chính xác dưới mili giây. Khi ánh xạ sang SQL timestamp, cần kiểm tra quy tắc timezone và precision của driver và database.

## 13. Tác động của biểu diễn byte đến bảo mật, hiệu năng và sao lưu

### Dung lượng và tốc độ I/O

Định dạng văn bản như JSON dễ kiểm tra bằng mắt, nhưng có thể chứa tên trường lặp lại và biểu diễn số bằng nhiều chữ số. Định dạng nhị phân được thiết kế tốt có thể giảm dung lượng hoặc chi phí parse cho từng loại tải, nhưng **không mặc định nhanh hơn trong mọi ứng dụng**. Kết quả phụ thuộc kích thước dữ liệu, schema, nén, truy cập ngẫu nhiên, CPU, mạng và pattern truy vấn.

Ví dụ, cột SQL có kiểu riêng thường giúp lọc và đánh index hơn một blob JSON nhị phân tự đóng gói. Ngược lại, định dạng cột như Parquet phù hợp một số truy vấn phân tích nhờ lưu theo cột và nén; nó không được tạo ra để thay thế mọi thao tác giao dịch nhỏ.

### Nén, mã hóa và checksum không đồng nghĩa

- **Encoding:** chuyển giá trị sang byte theo quy tắc, ví dụ UTF-8 hoặc `int32` big-endian.
- **Compression:** giảm số byte bằng cách khai thác cấu trúc/lặp lại; cần giải nén trước khi diễn giải theo định dạng gốc nếu giao thức quy định như vậy.
- **Encryption:** bảo vệ tính bí mật dữ liệu theo khóa và thuật toán; không tự cung cấp mọi đặc tính toàn vẹn nếu không có cơ chế xác thực phù hợp.
- **Checksum/hash:** hỗ trợ phát hiện thay đổi hoặc sai hỏng, nhưng checksum không có khóa không thay thế cơ chế xác thực chống sửa đổi có chủ ý.

Thiết kế cần phân biệt mục tiêu. Đưa dữ liệu nhạy cảm qua Base64 **không phải mã hóa bảo mật**. Ghi byte xuống đĩa cũng không tự tạo checksum, backup hay kiểm tra quyền truy cập.

### Backup và phục hồi

Sao lưu có thể chứa các byte của bảng dữ liệu, tệp, index, log và metadata. Nhưng **chỉ có dãy byte chưa đủ** để phục hồi thành dữ liệu logic có ý nghĩa nếu thiếu định dạng, version, khóa mã hóa, schema và cơ chế nhất quán.

Khi lập kế hoạch backup/restore:

- Xác định các thành phần vật lý và metadata cần khôi phục cùng nhau.
- Bảo đảm tương thích phiên bản engine và công cụ restore.
- Quản lý khóa mã hóa riêng và an toàn.
- Thử phục hồi để xác nhận dữ liệu logic đọc được, ràng buộc thỏa mãn và yêu cầu RPO/RTO khả thi.
- Tránh sao chép tệp dữ liệu đang thay đổi mà không sử dụng cơ chế sao lưu nhất quán do hệ quản trị hỗ trợ.

## 14. Những nhầm lẫn thường gặp

**“Dữ liệu logic là các byte được ghi lên đĩa.”** Không. Dữ liệu logic là giá trị và quy tắc có ý nghĩa; byte chỉ là một biểu diễn có thể dùng để lưu hoặc truyền giá trị ấy.

**“Nếu hai chuỗi nhìn giống nhau thì byte UTF-8 phải giống nhau.”** Không. Unicode normalization có thể tạo chuỗi code point khác nhau nhưng hiển thị tương tự.

**“`String.length()` là số byte của tên.”** Không. Java tính đơn vị mã UTF-16; phải encode theo charset cụ thể để lấy số byte.

**“Số nguyên `42` luôn là `00 00 00 2A`.”** Không. Nó có thể là text `34 32`, số 64-bit, little-endian, varint hoặc định dạng khác.

**“Đã có `@Entity` thì có thể đọc file database để tìm byte của trường Java.”** Không. ORM làm việc với mô hình quan hệ và engine; file nội bộ database phụ thuộc cách triển khai riêng.

**“`0.1` dưới dạng `double` chính xác như số thập phân 0.1.”** Không. Dấu phẩy động nhị phân có giới hạn biểu diễn; cần chọn kiểu phù hợp cho nghiệp vụ.

**“Serialize xong là dữ liệu đã tồn tại sau khi ứng dụng khởi động lại.”** Không. Serialization tạo một biểu diễn; persistence đòi hỏi lưu và khôi phục theo hợp đồng.

**“Có checksum tức là dữ liệu đã được bảo mật.”** Không. Checksum thường kiểm tra sai hỏng ngẫu nhiên; quyền truy cập, mã hóa và xác thực là các yêu cầu khác.

**“Thêm trường vào định dạng byte luôn đọc được bằng chương trình cũ.”** Không. Khả năng tương thích phụ thuộc cách bố trí và quy tắc bỏ qua trường/phiên bản.

## 15. Câu hỏi tự kiểm tra và bài tập thực hành

**Câu 1.** Hai byte `34 32` là số nguyên 42 hay chuỗi `"42"`?

**Đáp án:** Chỉ từ byte không thể kết luận. Theo UTF-8/ASCII, đây là chuỗi `"42"`. Theo số nguyên không dấu 16-bit big-endian, nó là `13362`. Cần biết schema và cách mã hóa.

**Câu 2.** Chương trình Java gửi `int` `0x01020304` qua mạng bằng big-endian. Bên nhận dùng little-endian. Điều gì xảy ra?

**Đáp án:** Bên nhận sẽ đọc sai giá trị nếu diễn giải cùng bốn byte theo little-endian; cả hai phải thống nhất thứ tự byte theo giao thức.

**Câu 3.** Vì sao `"😀".length()` là 2 nhưng UTF-8 chỉ có một emoji?

**Đáp án:** Java `String.length()` đếm đơn vị mã UTF-16; emoji này là một code point ngoài BMP nên chiếm hai code unit UTF-16, được encode thành bốn byte UTF-8.

**Câu 4.** Một hệ thống sử dụng `DECIMAL(19,2)` trong SQL và `BigDecimal` trong Java. Có được giả định byte mà database lưu giống byte của Java `BigDecimal` không?

**Đáp án:** Không. Kiểu dữ liệu logic có thể tương đương về giá trị, nhưng biểu diễn vật lý và cấu trúc nội bộ do mỗi runtime/database quyết định.

**Câu 5.** Hệ thống thêm trường `category` vào bản ghi phiên bản 2. Khi đọc tệp phiên bản 1, chương trình cần làm gì?

**Đáp án:** Nhận diện phiên bản, đọc theo format v1 và áp dụng chính sách chuyển đổi/mặc định có định nghĩa; không đọc quá số byte tồn tại hoặc tự đoán ý nghĩa trường.

**Câu 6.** Đã gọi `StockCodec.encode(stock)` và nhận `byte[]` trong Java. Tệp trên đĩa có được tạo ra chưa?

**Đáp án:** Chưa. `encode` chỉ tạo biểu diễn trong bộ nhớ. Phải có thao tác I/O riêng và xác định bảo đảm durability thích hợp.

**Bài thực hành A — đọc byte:** Hãy mã hóa số `258` thành số nguyên không dấu 16-bit theo big-endian và little-endian. Dự kiến: big-endian `01 02`, little-endian `02 01`. Viết `ByteBuffer` kiểm tra cả hai.

**Bài thực hành B — thiết kế codec:** Mở rộng `StockCodec` để lưu một trường `description` có thể `null`. Tự định nghĩa biểu diễn `null` khác chuỗi rỗng, tăng version, giới hạn độ dài và viết các trường hợp đọc v1/v2. Thử đưa byte thiếu, length âm, version không hỗ trợ hoặc UTF-8 sai để quan sát decoder từ chối input.

**Bài thực hành C — kết nối persistence:** Với một đối tượng `Product` có số tiền thập phân, hãy so sánh ba cách lưu: (1) các cột SQL có kiểu; (2) JSON UTF-8 trong một tệp; (3) blob byte tự định nghĩa. Nêu cách truy vấn theo giá tiền, cách migration, yêu cầu kiểm tra dữ liệu, khả năng backup/restore và chi phí bảo trì của từng cách.

Khi làm việc với persistence, luôn tách hai lớp: **ý nghĩa và ràng buộc của giá trị** ở tầng logic, cùng **quy tắc chuyển giá trị thành byte rồi đọc lại** ở tầng biểu diễn. Lựa chọn byte ảnh hưởng đến tính tương thích, dung lượng, hiệu năng và phục hồi; nhưng byte chỉ có ý nghĩa khi đi cùng kiểu, schema và hợp đồng dữ liệu rõ ràng.
