# MIN_VALUE, MAX_VALUE, SIZE và BYTES của các kiểu số nguyên trong Java

## 1. Bốn hằng số dùng để làm gì?

Khi làm việc với số nguyên, cần biết **miền giá trị** mà kiểu dữ liệu biểu diễn được và **độ rộng cố định** của kiểu đó. Java công bố bốn thông tin này qua các lớp bao (*wrapper class*) trong `java.lang`:

- `MIN_VALUE`: giá trị nhỏ nhất biểu diễn được.
- `MAX_VALUE`: giá trị lớn nhất biểu diễn được.
- `SIZE`: số **bit** của kiểu nguyên thủy tương ứng.
- `BYTES`: số **byte** của kiểu nguyên thủy tương ứng, với 1 byte = 8 bit.

Các tên hằng số thuộc lớp bao, chẳng hạn `Integer.MIN_VALUE`, **không thuộc từ khóa kiểu nguyên thủy** `int`. Đây là các trường `public static final` có thể truy cập mà không tạo đối tượng. Các kích thước dưới đây được ngôn ngữ Java quy định, độc lập hệ điều hành và kiến trúc CPU.

## 2. Bảng tra cứu đầy đủ

| Kiểu nguyên thủy | Lớp bao | `MIN_VALUE` | `MAX_VALUE` | `SIZE` (bit) | `BYTES` (byte) |
|---|---|---:|---:|---:|---:|
| `byte` | `Byte` | -128 | 127 | 8 | 1 |
| `short` | `Short` | -32_768 | 32_767 | 16 | 2 |
| `int` | `Integer` | -2_147_483_648 | 2_147_483_647 | 32 | 4 |
| `long` | `Long` | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 | 64 | 8 |
| `char` | `Character` | U+0000 (giá trị số 0) | U+FFFF (giá trị số 65_535) | 16 | 2 |

Bốn kiểu `byte`, `short`, `int` và `long` là **số nguyên có dấu**. Với kiểu có độ rộng `n` bit:

- Nhỏ nhất: \(-2^{n-1}\).
- Lớn nhất: \(2^{n-1}-1\).
- Tổng số mẫu bit: \(2^n\); số lượng giá trị âm nhiều hơn số lượng giá trị dương đúng một đơn vị vì có số 0.

`char` cũng là một kiểu nguyên thủy tích phân trong Java nhưng **không có dấu**: nó lưu một *UTF-16 code unit* từ 0 đến 65_535, chủ yếu để xử lý ký tự. Một ký tự Unicode ngoài BMP có thể cần **hai `char`** (surrogate pair), vì vậy `Character.SIZE = 16` không có nghĩa một ký tự Unicode luôn dài 16 bit.

`boolean` không có bộ hằng số `MIN_VALUE/MAX_VALUE/SIZE/BYTES` tương ứng; không suy ra kích thước bộ nhớ của `boolean` từ bảng này.

## 3. Đọc hằng số trực tiếp trong chương trình

Lưu tệp `IntegerMetadataDemo.java`:

```java
public class IntegerMetadataDemo {
    public static void main(String[] args) {
        System.out.printf("byte: [%d, %d], SIZE=%d, BYTES=%d%n",
                Byte.MIN_VALUE, Byte.MAX_VALUE, Byte.SIZE, Byte.BYTES);
        System.out.printf("short: [%d, %d], SIZE=%d, BYTES=%d%n",
                Short.MIN_VALUE, Short.MAX_VALUE, Short.SIZE, Short.BYTES);
        System.out.printf("int: [%d, %d], SIZE=%d, BYTES=%d%n",
                Integer.MIN_VALUE, Integer.MAX_VALUE, Integer.SIZE, Integer.BYTES);
        System.out.printf("long: [%d, %d], SIZE=%d, BYTES=%d%n",
                Long.MIN_VALUE, Long.MAX_VALUE, Long.SIZE, Long.BYTES);
        System.out.printf("char: [%d, %d], SIZE=%d, BYTES=%d%n",
                (int) Character.MIN_VALUE, (int) Character.MAX_VALUE,
                Character.SIZE, Character.BYTES);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac IntegerMetadataDemo.java
java IntegerMetadataDemo
```

Kết quả:

```text
byte: [-128, 127], SIZE=8, BYTES=1
short: [-32768, 32767], SIZE=16, BYTES=2
int: [-2147483648, 2147483647], SIZE=32, BYTES=4
long: [-9223372036854775808, 9223372036854775807], SIZE=64, BYTES=8
char: [0, 65535], SIZE=16, BYTES=2
```

Hai phép ép `(int)` ở dòng `char` giúp in **mã số code unit** thay vì ký tự không nhìn thấy. Với các kiểu có dấu, `MIN_VALUE/MAX_VALUE` là giá trị số; `SIZE/BYTES` mô tả độ rộng kiểu nguyên thủy, không phải kích thước đối tượng `Integer`, `Long`, v.v.

## 4. Khi nào dùng từng hằng số?

### 4.1. `MIN_VALUE` và `MAX_VALUE`: kiểm tra miền giá trị

Giả sử dữ liệu đầu vào là `long` nhưng API đích chỉ nhận `int`. Trước khi ép kiểu, kiểm tra:

```java
boolean fitsInt = value >= Integer.MIN_VALUE
        && value <= Integer.MAX_VALUE;
```

Nếu không nằm trong miền đó, phép ép `(int) value` sẽ **bỏ các bit cao** và có thể đổi thành một giá trị khác, không tự báo lỗi. Java còn cung cấp `Math.toIntExact(long)` để chuyển có kiểm tra, ném `ArithmeticException` khi ngoài miền `int`.

Đối với phép cộng, trừ, nhân số nguyên có dấu, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` khi muốn phát hiện tràn số thay vì nhận kết quả vòng lại (*wraparound*).

Lưu tệp `SafeIntegerDemo.java`:

```java
public class SafeIntegerDemo {
    public static void main(String[] args) {
        long value = 2_147_483_648L; // int MAX_VALUE + 1

        boolean fitsInt = value >= Integer.MIN_VALUE
                && value <= Integer.MAX_VALUE;
        System.out.println("fits int: " + fitsInt);
        System.out.println("cast (int): " + (int) value);

        try {
            Math.toIntExact(value);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: overflow");
        }

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }
    }
}
```

Chạy:

```bash
javac SafeIntegerDemo.java
java SafeIntegerDemo
```

Kết quả chính xác:

```text
fits int: false
cast (int): -2147483648
toIntExact: overflow
addExact: overflow
```

**Lưu ý:** kiểm tra miền bằng `MIN_VALUE/MAX_VALUE` phù hợp khi giá trị đầu vào đang ở kiểu rộng hơn. Nếu đã tính toán tràn bên trong `int` rồi mới so với `Integer.MAX_VALUE` thì đã quá muộn: biến chỉ còn chứa kết quả sau tràn.

### 4.2. `SIZE`: làm việc với bit

`Integer.SIZE` luôn là 32, `Long.SIZE` luôn là 64. Các hằng số hữu ích cho thuật toán bit, mặt nạ, giao thức nhị phân và biểu diễn bit:

```java
int bitCount = Integer.SIZE;  // 32
int highBitMask = 1 << (Integer.SIZE - 1); // bit dấu của int
long twoTo32 = 1L << Integer.SIZE; // 4294967296L
```

Đừng viết `1 << 32` để lấy \(2^{32}\): toán hạng trái `int` khiến Java chỉ dùng 5 bit thấp của khoảng dịch; `1 << 32` tương đương `1 << 0` và bằng **1**. Dùng `1L` khi phép dịch phải tính trên `long`.

### 4.3. `BYTES`: xác định độ rộng dữ liệu nhị phân

`Integer.BYTES` bằng 4 và `Long.BYTES` bằng 8. Ví dụ: một bản ghi nhị phân gồm một `int` và một `long` có tổng độ rộng phần dữ liệu là:

```java
int recordBytes = Integer.BYTES + Long.BYTES; // 12
```

Khi truyền dữ liệu, cần quy định thêm **thứ tự byte** (*endianness*). Chẳng hạn `ByteBuffer` mặc định dùng big-endian, có thể đổi qua `order(ByteOrder.LITTLE_ENDIAN)`. `BYTES` chỉ nói số byte, không nói thứ tự byte và **không bao gồm** header, padding, bộ nhớ đối tượng hoặc overhead của collection.

## 5. Những bẫy thường gặp

### 5.1. Tràn số không tự phát sinh ngoại lệ

```java
int wrapped = Integer.MAX_VALUE + 1; // -2147483648
long wrappedLong = Long.MAX_VALUE + 1; // Long.MIN_VALUE
```

Phép cộng trên số nguyên có dấu của Java lấy kết quả theo độ rộng cố định; muốn báo lỗi dùng phương thức `Exact` hoặc chuyển sang `BigInteger` nếu cần số nguyên không bị giới hạn ở 64 bit.

### 5.2. `MIN_VALUE` không đối xứng với `MAX_VALUE`

Vì số âm nhiều hơn số dương một giá trị:

```java
System.out.println(-Integer.MIN_VALUE);
System.out.println(Math.abs(Integer.MIN_VALUE));
```

Cả hai dòng đều in `-2147483648` do kết quả dương không biểu diễn được trong `int`. Tương tự, `Integer.MIN_VALUE / -1` trả về `Integer.MIN_VALUE` (trường hợp tràn đặc biệt của phép chia nguyên). Dùng `Math.negateExact` nếu cần bắt lỗi khi đổi dấu; với giá trị tuyệt đối của số cực tiểu, dùng kiểu rộng hơn hoặc `BigInteger`.

### 5.3. Hằng số thuộc lớp bao, không biểu thị dung lượng đối tượng

`Integer.BYTES == 4` mô tả **giá trị `int` 32 bit**. Nó không cam kết một đối tượng `new Integer(...)` chiếm đúng 4 byte; object header, căn chỉnh và cơ chế VM làm dung lượng khác đi. Trong Java hiện đại cũng nên dùng `Integer.valueOf(...)` hoặc autoboxing, tránh constructor wrapper đã bị deprecated.

### 5.4. Ép kiểu, thăng cấp số học và hằng `long`

- Trong biểu thức số học, `byte`, `short` và `char` thường được thăng cấp thành `int`: `Byte.MAX_VALUE + 1` có kiểu `int` và bằng 128.
- `(byte) 128` cho kết quả -128 vì giữ lại 8 bit thấp.
- Hằng số `long` nên có hậu tố `L`: `3_000_000_000L`; dấu gạch dưới chỉ tăng khả năng đọc, không thay đổi giá trị.
- Với số nguyên không dấu lưu trong các bit của `int/long`, xem các API như `Integer.compareUnsigned`, `Integer.toUnsignedLong`, `Long.compareUnsigned`. Đừng suy ra miền không dấu từ `Integer.MIN_VALUE/MAX_VALUE` vì hai hằng số này là miền **có dấu**.

### 5.5. Đừng nhầm `Integer.MIN_VALUE` với `Double.MIN_VALUE`

`Integer.MIN_VALUE` là **số âm nhỏ nhất** của `int`. Ngược lại, `Float.MIN_VALUE` và `Double.MIN_VALUE` là **số dương khác 0 nhỏ nhất** có thể biểu diễn (giá trị dưới chuẩn), không phải số âm thấp nhất. Với số thực, phải xét thêm `MAX_VALUE`, dấu âm, vô cực, NaN và độ chính xác; không áp dụng máy móc bảng số nguyên.

## 6. Cách chọn và sử dụng trong thực tế

1. Chọn `int` cho số nguyên thông dụng nằm trong miền 32 bit; dùng `long` cho số lớn hơn hoặc thời gian/đếm có thể vượt giới hạn `int`.
2. Khi nhận dữ liệu lớn rồi chuyển sang kiểu hẹp, xác nhận miền bằng `MIN_VALUE/MAX_VALUE` hoặc `Math.toIntExact`.
3. Khi tính toán mà overflow gây lỗi nghiệp vụ, dùng các phép toán `Math.*Exact` và xử lý ngoại lệ thích hợp.
4. Khi thao tác bit hoặc định dạng nhị phân, lấy `SIZE/BYTES` từ wrapper để bộc lộ rõ độ rộng; chỉ rõ endianness của định dạng dữ liệu.
5. Với số lớn hơn giới hạn `long`, dùng `java.math.BigInteger`; `BigInteger` không có bộ `MIN_VALUE/MAX_VALUE/SIZE/BYTES` cố định tương ứng vì độ dài số có thể tăng.

## 7. Tự kiểm tra

**Câu 1.** `Short.SIZE` và `Short.BYTES` lần lượt bằng bao nhiêu?  
**Đáp án:** 16 bit và 2 byte.

**Câu 2.** Vì sao `Integer.MIN_VALUE` bằng -2_147_483_648 trong khi `Integer.MAX_VALUE` chỉ bằng 2_147_483_647?  
**Đáp án:** một trong 32 bit dành cho dấu; miền signed 32-bit là \([-2^{31},2^{31}-1]\), gồm cả 0.

**Câu 3.** Ép `2_147_483_648L` sang `int` có ném ngoại lệ không?  
**Đáp án:** không; ép trực tiếp cho -2_147_483_648. `Math.toIntExact` sẽ ném `ArithmeticException`.

**Câu 4.** `Character.SIZE = 16` có đảm bảo mọi ký tự Unicode nằm trong một `char` không?  
**Đáp án:** không; một code point ngoài BMP cần hai UTF-16 code unit, tức hai `char`.

**Câu 5.** Có thể dùng `Integer.BYTES` để đo bộ nhớ của `Integer` object không?  
**Đáp án:** không; nó là độ rộng giá trị nguyên thủy `int`, không phải kích thước object trong heap.

**Ghi nhớ:** `MIN_VALUE/MAX_VALUE` trả lời **giá trị nào biểu diễn được?**; `SIZE/BYTES` trả lời **kiểu nguyên thủy rộng bao nhiêu bit/byte?**. Đây là hai nhóm hằng số khác mục đích, nhưng thường dùng cùng nhau để xử lý số nguyên an toàn và dữ liệu nhị phân đúng định dạng.
