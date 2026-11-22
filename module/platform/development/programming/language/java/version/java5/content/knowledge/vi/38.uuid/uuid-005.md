# Truy cập hai phần 64 bit của UUID

## 1. Mục đích: giữ đủ định danh khi làm việc với dữ liệu nhị phân

Một UUID mang giá trị 128 bit. Java không có kiểu nguyên thủy số nguyên 128 bit, nên lớp `UUID` cho phép lấy giá trị qua hai số `long`, mỗi số 64 bit.

Cách nhìn này hữu ích khi cần ghi một giao thức nhị phân, chuyển thành 16 byte, hoặc tích hợp với cấu trúc dữ liệu lưu hai trường 64 bit. Nếu chỉ truyền mã qua một API văn bản thông thường, dùng dạng chuỗi UUID thường dễ đọc và ít sai hơn.

Hai phương thức cần biết:

| Phương thức | Kết quả |
| --- | --- |
| `getMostSignificantBits()` | 64 bit cao của UUID |
| `getLeastSignificantBits()` | 64 bit thấp của UUID |

Constructor `new UUID(high, low)` dựng lại giá trị theo đúng thứ tự đó. `UUID` là kiểu bất biến; lấy các nửa hoặc tạo đối tượng mới không sửa đối tượng gốc. Xem [Java UUID API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html).

Các getter này trả về dữ liệu của UUID đang có. Chúng không tạo thêm bit ngẫu nhiên, không tính giá trị băm và không phải là hai định danh độc lập.

## 2. “Cao” và “thấp” nghĩa là gì?

Xét giá trị cố định:

```text
8899aabb-ccdd-4eef-8011-223344556677
```

Bỏ các dấu gạch nối để nhìn đủ 32 chữ số hex, rồi tách sau 16 chữ số:

```text
8899aabbccdd4eef | 8011223344556677
    high        |       low
  16 hex = 64 bit | 16 hex = 64 bit
```

“Cao/thấp” nói về trọng số bit trong toàn giá trị. Nó không có nghĩa nửa cao được tạo trước, nửa thấp kém quan trọng hoặc nửa cao là thời gian tạo.

Dấu gạch nối thuộc dạng biểu diễn chuỗi; chúng không xuất hiện trong hai `long`. Ranh giới giữa hai nửa trùng với vị trí giữa nhóm thứ ba và nhóm thứ tư của chuỗi chuẩn. Vì vậy không được lấy `substring(0, 16)` trên chuỗi còn dấu nối rồi cho rằng đã thu được 64 bit cao: 16 ký tự ấy chứa cả ký hiệu phân nhóm.

Một nửa bị mất thì không thể tái lập chắc chắn toàn bộ mã. Hai UUID có thể chung nửa cao nhưng khác nửa thấp, hoặc ngược lại. Không thay UUID bằng chỉ một getter để “tiết kiệm” dung lượng mà vẫn kỳ vọng giữ nguyên định danh.

## 3. Vì sao các số `long` có thể âm?

`long` trong Java là số nguyên 64 bit có dấu. Khi bit đầu bằng 1, cùng mẫu 64 bit đó được diễn giải thành số âm theo biểu diễn bù hai.

Ví dụ, nửa cao bắt đầu bằng `8`, tức bốn bit đầu `1000`. Nửa thấp cũng bắt đầu bằng `8`. Vì vậy cả hai getter ở ví dụ này đều trả về `long` âm. Không có bit nào bị mất và UUID không trở thành “UUID âm”.

Cần phân biệt:

- Mẫu bit: dữ liệu 64 bit được giữ nguyên.
- Giá trị thập phân có dấu: cách `long` thường được in.
- Giá trị thập phân không dấu: cách diễn giải toàn bộ 64 bit trong miền `0` đến `2^64 - 1`.

`Long.toUnsignedString(value)` giúp in theo cách thứ ba. Nó trả chuỗi, không biến `long` thành một kiểu nguyên thủy mới. Khi đọc lại chuỗi thập phân không dấu, dùng API tương ứng `Long.parseUnsignedLong(text)`; đừng mặc định `Long.parseLong(text)` chấp nhận mọi giá trị trong miền không dấu. Xem [Java Long API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).

Đối với khảo sát bit, hex thường thuận tiện hơn:

```java
System.out.printf("%016x%n", high);
System.out.printf("%016x%n", low);
```

Đây là đoạn minh họa, cần các biến `high` và `low` trong chương trình bên dưới. Mỗi dòng in đủ 16 chữ số; số 0 đầu được giữ khi cần. Dấu âm không xuất hiện vì đang nhìn biểu diễn hex của mẫu bit.

Không áp dụng `Math.abs()` để “sửa” số âm. Việc đổi giá trị số sẽ làm thay đổi mẫu bit, nên constructor sau đó có thể tạo UUID khác. Ngoài ra, trị nhỏ nhất của `long` không có đối số dương tương ứng trong cùng kiểu.

## 4. Chương trình đầy đủ: tách, dựng lại và chuyển thành byte

Lưu thành `UuidHalvesDemo.java`. Chương trình biên dịch trên JDK 17 trở lên, dùng thư viện chuẩn:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.UUID;

public class UuidHalvesDemo {
    public static void main(String[] args) {
        UUID id = UUID.fromString("8899aabb-ccdd-4eef-8011-223344556677");
        long high = id.getMostSignificantBits();
        long low = id.getLeastSignificantBits();

        System.out.printf("highHex=%016x%n", high);
        System.out.printf("lowHex=%016x%n", low);
        System.out.println("highNegative=" + (high < 0));
        System.out.println("lowNegative=" + (low < 0));
        System.out.println("highUnsigned=" + Long.toUnsignedString(high));
        System.out.println("lowUnsigned=" + Long.toUnsignedString(low));

        UUID restored = new UUID(high, low);
        UUID swapped = new UUID(low, high);
        System.out.println("restored=" + restored);
        System.out.println("sameValue=" + id.equals(restored));
        System.out.println("swappedSame=" + id.equals(swapped));

        byte[] bytes = toBytes(id);
        System.out.println("bytes=" + bytes.length);
        System.out.println("hexBytes=" + HexFormat.of().formatHex(bytes));
        System.out.println("byteRoundTrip=" + id.equals(fromBytes(bytes)));

        System.out.println("shift64Same=" + ((high << 64) == high));
        try {
            fromBytes(new byte[15]);
        } catch (IllegalArgumentException ex) {
            System.out.println("shortInput=rejected");
        }
    }

    private static byte[] toBytes(UUID id) {
        return ByteBuffer.allocate(16)
                .order(ByteOrder.BIG_ENDIAN)
                .putLong(id.getMostSignificantBits())
                .putLong(id.getLeastSignificantBits())
                .array();
    }

    private static UUID fromBytes(byte[] bytes) {
        if (bytes.length != 16) {
            throw new IllegalArgumentException("UUID needs exactly 16 bytes");
        }
        ByteBuffer buffer = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidHalvesDemo.java
java UuidHalvesDemo
```

Stdout:

```text
highHex=8899aabbccdd4eef
lowHex=8011223344556677
highNegative=true
lowNegative=true
highUnsigned=9843086184167591663
lowUnsigned=9228194715043980919
restored=8899aabb-ccdd-4eef-8011-223344556677
sameValue=true
swappedSame=false
bytes=16
hexBytes=8899aabbccdd4eef8011223344556677
byteRoundTrip=true
shift64Same=true
shortInput=rejected
```

Cách đọc kết quả:

1. Hai dòng hex ghép lại thành đúng 32 chữ số của UUID, không có dấu nối.
2. Hai dòng `Negative=true` chỉ nói về cách Java diễn giải `long` có dấu.
3. `restored` giống mã ban đầu vì constructor nhận đúng thứ tự cao rồi thấp.
4. `sameValue=true` dùng `equals()` để so giá trị; `swappedSame=false` cho thấy đổi thứ tự hai nửa làm đổi mã ở ví dụ này.
5. Mảng nhị phân có đúng 16 byte; `byteRoundTrip=true` xác nhận chuyển đi rồi đọc lại bảo toàn định danh.
6. Mảng 15 byte bị từ chối rõ ràng theo hợp đồng của hàm giải mã.

Mọi giá trị trong stdout là cố định vì chương trình dùng một UUID cố định, không dùng bộ sinh ngẫu nhiên.

## 5. Quy ước 16 byte phải giống nhau ở bên ghi và bên đọc

Trong ví dụ, hàm `toBytes()` thực hiện:

```text
nửa cao → 8 byte đầu
nửa thấp → 8 byte sau
trong mỗi nửa: byte có trọng số cao đi trước
```

`ByteOrder.BIG_ENDIAN` nêu rõ quy ước thứ tự byte. Hàm `fromBytes()` dùng cùng quy ước và đọc hai `long` theo đúng thứ tự. Các thao tác `putLong()`/`getLong()` và byte order được mô tả trong [Java ByteBuffer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).

Đây là hợp đồng mã hóa của hai hàm trong bài. Khi tích hợp với cơ sở dữ liệu hoặc thư viện khác, phải kiểm tra định dạng của bên kia. Một hệ thống có thể có thao tác sắp xếp lại byte nhằm phục vụ cách lưu riêng; không được đoán rằng “đều là 16 byte” thì chắc chắn đọc cùng cách.

Đổi cả bên ghi lẫn bên đọc sang một quy ước khác có thể vẫn cho phép đi/về trong nội bộ, nhưng chưa chứng minh tương thích với đối tác. Vì vậy ngoài kiểm tra đi/về, cần có ít nhất một giá trị mẫu mà cả hai bên thống nhất chuỗi UUID và 16 byte tương ứng.

Hàm giải mã kiểm tra `bytes.length == 16` trước khi đọc. Nếu chỉ gọi `getLong()` hai lần, dữ liệu thiếu có thể gây lỗi bộ đệm; dữ liệu thừa lại có thể bị bỏ qua. Kiểm tra kích thước làm hợp đồng của một UUID riêng lẻ rõ ràng hơn. Ví dụ giả định đầu vào không `null`; nếu nguồn có thể trả `null`, quyết định và xử lý trường hợp ấy tại ranh giới ứng dụng.

## 6. Các bẫy khi tự ghép hai nửa

### Không ghép thành một `long` bằng dịch 64 bit

Biểu thức sau không tạo ra số 128 bit:

```java
long wrong = (high << 64) | low;
```

Đây là mã minh họa lỗi, không nên dùng. Với toán hạng trái kiểu `long`, Java chỉ dùng sáu bit thấp của khoảng dịch, nên dịch 64 tương đương dịch 0. Kết quả vẫn là một số 64 bit. Vì thế chương trình in `shift64Same=true`. Quy tắc nằm trong [JLS 15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.19).

Nếu cần giữ UUID, dùng đối tượng `UUID`, cặp `long` có thứ tự rõ ràng hoặc mảng 16 byte. Nếu thật sự cần số nguyên lớn để tính toán, chọn `BigInteger` và quy định cách diễn giải không dấu; việc đó là một yêu cầu khác với lưu định danh.

### Không chuyển qua `int`, `float` hoặc `double`

Ép nửa 64 bit về `int` bỏ mất 32 bit. Chuyển qua kiểu dấu phẩy động cũng không bảo toàn mọi số nguyên 64 bit. Dữ liệu nhìn gần giống khi in số không chứng minh định danh còn đúng.

Tương tự, khi đi qua định dạng trao đổi được xử lý bằng số thực ở bên nhận, cần bảo toàn giá trị bằng biểu diễn được thỏa thuận, chẳng hạn chuỗi UUID chuẩn. Không tách thành hai con số lớn rồi mặc định mọi ngôn ngữ đều đọc chính xác như Java.

### Constructor không phải bộ sinh UUID

`new UUID(high, low)` nhận những bit được đưa vào. Nó không tự tạo định danh mới duy nhất, không kiểm chứng chất lượng dữ liệu và không tự sửa các bit version/variant theo ý muốn.

Mục đích của constructor trong bài là phục hồi một giá trị đã có. Nếu đang cần sinh định danh, dùng cơ chế sinh đúng với hợp đồng của hệ thống thay vì tự ghép các số tùy ý.

## 7. Kiểm tra điều gì khi áp dụng?

Với một hàm mã hóa UUID vào giao thức hoặc kho dữ liệu, các điểm kiểm tra có ích là:

- Đọc đủ cả hai nửa, đúng thứ tự.
- Không chuyển trung gian qua kiểu làm mất bit.
- Cùng byte order ở hai đầu.
- Kích thước dữ liệu đúng 16 byte.
- So giá trị sau khi đọc lại bằng `equals()`.
- Dùng mẫu có bit đầu bằng 1 và có các byte khác nhau để dễ phát hiện lỗi dấu hoặc đảo thứ tự.

Đừng chỉ kiểm tra UUID toàn số 0: đổi thứ tự hai nửa hoặc đảo các byte 0 vẫn khó lộ lỗi. Giá trị cố định trong chương trình được chọn để hai nửa khác nhau và cả hai có dấu âm khi diễn giải như `long`.

Việc tách nửa không thay thế kiểm tra quyền truy cập hoặc kiểm tra sự tồn tại của đối tượng mang mã đó. Đây là thao tác biểu diễn dữ liệu, không phải xác thực danh tính.

## 8. Tự kiểm tra

1. `getMostSignificantBits()` trả về 64 bit hay toàn bộ 128 bit?
2. Vì sao constructor phải nhận `high` trước `low`?
3. Nếu `low < 0`, có cần lấy trị tuyệt đối trước khi lưu không?
4. `(high << 64) | low` có tạo ra số 128 bit không?
5. Hai đầu cùng dùng 16 byte đã đủ để bảo đảm tương thích chưa?

Đáp án: (1) chỉ 64 bit cao; (2) thứ tự tham số xác định vị trí bit trong UUID; (3) không, cần giữ nguyên mẫu bit; (4) không, kết quả vẫn là `long` và khoảng dịch 64 tương đương 0; (5) chưa, phải thống nhất thứ tự hai nửa và thứ tự byte.
