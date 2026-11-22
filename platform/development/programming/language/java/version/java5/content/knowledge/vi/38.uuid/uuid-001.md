# Cấu trúc định danh UUID 128 bit

## 1. Một giá trị, nhiều cách biểu diễn

UUID (Universally Unique Identifier) là một định danh có độ rộng cố định 128 bit. Hãy hình dung một mã gắn với đối tượng như đơn hàng: máy tính cần giữ nguyên mã đó khi lưu, gửi và đọc lại. Bài này giải thích cấu trúc của mã, chưa đi sâu vào thiết kế bộ sinh hay chọn khóa cơ sở dữ liệu.

Cùng một UUID có thể được nhìn dưới ba dạng:

- Giá trị nhị phân: 128 bit, tức 16 byte.
- Chuỗi để con người đọc: 32 chữ số thập lục phân và 4 dấu gạch nối, tổng cộng 36 ký tự.
- Trong Java: đối tượng `java.util.UUID`, có thể lấy ra hai nửa 64 bit.

Đừng đồng nhất kích thước giá trị với dung lượng đối tượng Java hoặc chuỗi trong bộ nhớ. Một đối tượng còn có phần quản lý của JVM; chuỗi còn có dữ liệu biểu diễn riêng. “UUID 16 byte” nói về phần giá trị nhị phân.

Ví dụ cố định dùng xuyên suốt bài:

```text
123e4567-e89b-42d3-a456-426614174000
```

Đây là giá trị được chọn để khảo sát bit; bài không khẳng định nó được sinh ngẫu nhiên trong một hệ thống thực tế.

## 2. Vì sao 32 chữ số lại biểu diễn được 128 bit?

Một chữ số thập lục phân, từ `0` đến `f`, biểu diễn 4 bit. Vì vậy:

```text
32 chữ số × 4 bit = 128 bit
128 bit ÷ 8       = 16 byte
32 chữ số + 4 dấu '-' = 36 ký tự
```

Năm nhóm chữ số có độ dài `8-4-4-4-12`:

| Nhóm | Giá trị ví dụ | Số chữ số | Số bit |
| --- | --- | ---: | ---: |
| 1 | 123e4567 | 8 | 32 |
| 2 | e89b | 4 | 16 |
| 3 | 42d3 | 4 | 16 |
| 4 | a456 | 4 | 16 |
| 5 | 426614174000 | 12 | 48 |

Tổng là `32 + 16 + 16 + 16 + 48 = 128` bit. Dấu gạch nối chỉ giúp phân nhóm khi viết chuỗi, không chiếm bit trong giá trị UUID. Chữ hoa hoặc chữ thường của chữ số hex không làm đổi giá trị; `UUID.toString()` cho biểu diễn chuẩn dùng chữ thường.

## 3. Hai vị trí cần đọc: version và variant

Với UUID thuộc biến thể thông dụng do IETF quy định, mẫu chuỗi là:

```text
xxxxxxxx-xxxx-Vxxx-Nxxx-xxxxxxxxxxxx
              ^    ^
           version variant
```

`V` là chữ số đầu nhóm thứ ba, mang 4 bit version. `N` là chữ số đầu nhóm thứ tư; hai bit đầu của nó là `10`, nhận diện variant. Vì thế `N` có thể là `8`, `9`, `a` hoặc `b`.

Nếu đánh số bit từ 0 ở đầu trái, version nằm ở bit 48–51, còn tiền tố variant nằm ở bit 64–65. Đây là quy ước đánh số từ trái, cần phân biệt với vị trí dịch bit trong một số `long`.

Các quy tắc bố cục này theo [RFC 9562, mục 4](https://www.rfc-editor.org/rfc/rfc9562.html#section-4).

Áp dụng vào ví dụ:

```text
123e4567-e89b-42d3-a456-426614174000
              4    a

4 hex = 0100 nhị phân  → version 4
a hex = 1010 nhị phân  → hai bit đầu 10
```

Version mô tả cách diễn giải phần còn lại; variant xác định họ bố cục. Hai khái niệm này không thay thế nhau. Trong Java, `id.variant()` trả về số `2` cho tiền tố `10`; nó không trả về chữ số `a` vừa nhìn thấy.

Version cũng không phải phiên bản Java: một UUID version 4 không có nghĩa là tính năng của Java 4.

Với version 4, 4 bit version và 2 bit variant đã cố định, nên còn `128 - 4 - 2 = 122` bit cho phần ngẫu nhiên. Không thể lấy `2^128` làm số khả năng của riêng UUIDv4. Việc có đủ hình dạng và đúng các bit đánh dấu chỉ cho biết cấu trúc; nó không chứng minh nguồn ngẫu nhiên tốt hay giá trị chưa từng được tạo.

Các phiên bản khác vẫn dùng khung 128 bit nhưng phân bổ nội dung khác. Ví dụ, version 7 có thành phần thời gian; vì vậy không được xem mọi UUID là một khối ngẫu nhiên hoặc suy thời điểm tạo từ bất kỳ UUID nào. Bài không dùng tên các trường thời gian của một phiên bản để gán nghĩa cho mọi phiên bản. Xem [RFC 9562, các bố cục UUID](https://www.rfc-editor.org/rfc/rfc9562.html#section-5).

## 4. Hai nửa 64 bit trong Java

`UUID` là kiểu bất biến. Các phương thức `getMostSignificantBits()` và `getLeastSignificantBits()` trả về hai phần của giá trị; có thể dựng lại bằng `new UUID(high, low)`. Đây là API vẫn dùng được trên Java hiện đại. Xem [Java UUID API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html).

Với ví dụ đã chọn, bỏ dấu gạch nối rồi tách sau 16 chữ số hex:

```text
123e4567e89b42d3 | a456426614174000
  64 bit cao    |    64 bit thấp
```

Từ “cao/thấp” mô tả trọng số bit của toàn giá trị, không phải thứ tự sinh hoặc mức độ quan trọng nghiệp vụ.

Java dùng `long` có dấu. Nửa thấp bắt đầu bằng `a`, tức bit đầu là 1, nên khi diễn giải như `long` có dấu nó mang giá trị âm. Điều này không làm hỏng UUID. Cả 64 bit vẫn được giữ nguyên; chỉ cách diễn giải thành số thập phân có dấu thay đổi. Xem [Java Long API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).

Để đọc version bằng phép toán bit từ `high`:

```java
int version = (int) ((high >>> 12) & 0xFL);
```

Đây là đoạn minh họa, cần biến `high` của ví dụ đầy đủ bên dưới. Dịch phải không dấu 12 vị trí đưa bốn bit version về cuối; mặt nạ `0xF` giữ đúng bốn bit đó. Trong mã ứng dụng thông thường, dùng `id.version()` sẽ dễ đọc hơn.

Tương tự, `low >>> 62` lấy hai bit đầu của nửa thấp. Kết quả nhị phân `10` chính là tiền tố variant đang khảo sát. Không dùng phép này như hàm phân loại tổng quát mọi variant; `id.variant()` đã đảm nhiệm việc đó.

## 5. Chương trình chạy đầy đủ: chuỗi → bit → byte → UUID

Lưu thành `UuidStructureDemo.java`. Ví dụ chạy trên JDK 17 trở lên, không dùng thư viện ngoài:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.UUID;

public class UuidStructureDemo {
    public static void main(String[] args) {
        UUID id = UUID.fromString("123e4567-e89b-42d3-a456-426614174000");
        long high = id.getMostSignificantBits();
        long low = id.getLeastSignificantBits();

        System.out.println("uuid=" + id);
        System.out.println("textLength=" + id.toString().length());
        System.out.println("version=" + id.version());
        System.out.println("variant=" + id.variant());
        System.out.printf("high=%016x%n", high);
        System.out.printf("low=%016x%n", low);
        System.out.println("lowIsNegative=" + (low < 0));
        System.out.println("manualVersion=" + ((high >>> 12) & 0xFL));
        System.out.println("variantPrefix=" + Long.toBinaryString(low >>> 62));

        byte[] bytes = ByteBuffer.allocate(16)
                .order(ByteOrder.BIG_ENDIAN)
                .putLong(high)
                .putLong(low)
                .array();

        System.out.println("byteLength=" + bytes.length);
        System.out.println("hex=" + HexFormat.of().formatHex(bytes));

        ByteBuffer input = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN);
        UUID restored = new UUID(input.getLong(), input.getLong());
        System.out.println("roundTrip=" + id.equals(restored));

        UUID generated = UUID.randomUUID();
        System.out.println("generatedVersion=" + generated.version());
        System.out.println("generatedVariant=" + generated.variant());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidStructureDemo.java
java UuidStructureDemo
```

Stdout:

```text
uuid=123e4567-e89b-42d3-a456-426614174000
textLength=36
version=4
variant=2
high=123e4567e89b42d3
low=a456426614174000
lowIsNegative=true
manualVersion=4
variantPrefix=10
byteLength=16
hex=123e4567e89b42d3a456426614174000
roundTrip=true
generatedVersion=4
generatedVariant=2
```

Các bước quan sát:

1. `fromString()` đọc chuỗi đã chọn, không tạo định danh mới.
2. `%016x` in mỗi nửa thành đúng 16 chữ số hex, giúp nhìn đủ các bit kể cả khi có số 0 ở đầu.
3. Hai `putLong()` lần lượt ghi nửa cao và nửa thấp thành 16 byte.
4. Hai `getLong()` đọc cùng thứ tự, rồi constructor dựng lại đúng giá trị.
5. `equals()` xác nhận phép đi và về bảo toàn UUID. Không dùng `==` để kiểm tra hai đối tượng có cùng giá trị.
6. `randomUUID()` tạo UUIDv4 mới. Bản thân mã ngẫu nhiên thay đổi giữa các lần chạy; chương trình chỉ in version/variant nên hai dòng cuối vẫn cố định.

Các tên phương thức, tính bất biến, đối chiếu giá trị và cách sinh UUIDv4 được mô tả trong [Java UUID API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html).

`ByteOrder.BIG_ENDIAN` được ghi rõ để bên đọc và bên ghi thống nhất thứ tự byte: byte có trọng số cao đi trước. Đây là hợp đồng mã hóa của ví dụ, không phải lời khẳng định rằng mọi hệ thống lưu UUID đều có cùng thứ tự byte. Xem [Java ByteBuffer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).

Ví dụ không lấy 16 ký tự đầu của chuỗi để làm “16 byte UUID”. Khi cần dữ liệu nhị phân, phải giải mã đúng giá trị hoặc ghi đủ hai nửa như trên; byte của văn bản có cả dấu gạch nối là dữ liệu biểu diễn chuỗi.

## 6. Áp dụng và lỗi dễ gặp

### Định dạng và chính sách chấp nhận là hai lớp riêng

Khi nhận UUID từ HTTP hoặc tệp, hãy xác định hợp đồng đầu vào. Dạng chuỗi chuẩn dài 36 ký tự không đồng nghĩa rằng mọi chuỗi dài 36 đều hợp lệ. Ngược lại, chỉ gọi parser cũng không thay thế chính sách “chỉ nhận UUIDv4 thuộc variant IETF” nếu nghiệp vụ có yêu cầu đó.

Một chuỗi có thể đọc thành UUID nhưng không đáp ứng quy tắc riêng của ứng dụng. Ví dụ, constructor nhận hai `long` chỉ biểu diễn bit được truyền vào; nó không tự biến chúng thành định danh ngẫu nhiên đáng tin cậy. Tránh sửa tùy tiện chữ số version/variant để “nâng cấp” một mã có sẵn: sửa bit tạo ra một giá trị khác, không thực hiện thuật toán sinh của phiên bản mới.

### Không cắt bỏ các bit chỉ vì có hai nửa

Chỉ lưu `getMostSignificantBits()`, `getLeastSignificantBits()` hoặc `hashCode()` sẽ không giữ toàn bộ UUID. Với hai mã khác nhau ở nửa bị bỏ, dữ liệu rút gọn có thể giống nhau. Muốn bảo toàn định danh, phải giữ đủ 128 bit hoặc biểu diễn chuỗi tương đương.

### Thứ tự byte phải được thống nhất khi trao đổi

Nếu một bên ghi nửa cao trước nhưng bên kia đọc nửa thấp trước, cả hai có thể vẫn tạo được đối tượng UUID, nhưng đó là mã khác. Khi tích hợp với hệ thống khác, kiểm tra tài liệu định dạng và thử đi/về bằng một giá trị cố định có nhiều chữ số khác nhau như ví dụ; không chỉ thử giá trị toàn số 0.

### Định danh không tự cấp quyền

Biết hình dạng UUID không chứng minh mã đó thuộc một bản ghi hiện hữu hoặc người gửi được phép truy cập bản ghi. Chẳng hạn, API nhận mã đơn hàng vẫn phải kiểm tra quyền xem đơn hàng. Cấu trúc 128 bit giải quyết biểu diễn định danh; kiểm tra tồn tại và kiểm tra quyền là trách nhiệm riêng của ứng dụng.

## 7. Tự kiểm tra

1. Vì sao chuỗi có 36 ký tự nhưng phần giá trị chỉ có 16 byte?
2. Trong `123e4567-e89b-42d3-a456-426614174000`, chữ số nào cho biết version?
3. Vì sao đổi chữ `a` đầu nhóm thứ tư thành `b` vẫn giữ tiền tố variant `10` nhưng làm đổi UUID?
4. Nửa `long` âm có cho thấy UUID bị lỗi không?
5. Nếu bỏ nửa thấp và giữ nửa cao, có thể phục hồi chắc chắn UUID gốc không?

Đáp án ngắn: (1) 32 chữ số hex mã hóa 128 bit, bốn dấu nối chỉ là ký hiệu; (2) `4` đầu nhóm thứ ba; (3) `a = 1010`, `b = 1011`, hai bit đầu không đổi nhưng bit dữ liệu đã đổi; (4) không, do cách diễn giải có dấu của `long`; (5) không, thông tin 64 bit đã bị mất.
