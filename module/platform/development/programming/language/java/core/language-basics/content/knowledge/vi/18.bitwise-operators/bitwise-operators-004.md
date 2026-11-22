# Dịch phải có dấu `>>` và không dấu `>>>` — Java 17+

## 1. Mục tiêu và khác biệt quan trọng nhất

Java có hai toán tử **dịch bit sang phải**:

- **`>>` — dịch phải có dấu** (*signed/arithmetic right shift*): đẩy các bit sang phải, lấp các vị trí mới bên trái bằng **bit dấu** của toán hạng sau khi nâng kiểu. Số âm tiếp tục có bit dấu 1.
- **`>>>` — dịch phải không dấu** (*unsigned/logical right shift*): đẩy các bit sang phải, **luôn lấp bằng bit 0** bên trái. Với số âm, kết quả có thể trở thành số dương rất lớn.

~~~java
int number = -8;
System.out.println(number >> 2);  // -2
System.out.println(number >>> 2); // 1073741822
~~~

Cả hai đều thao tác trên **biểu diễn bit**; chúng không phải toán tử so sánh `>` và cũng không chuyển kiểu `int` thành một kiểu unsigned mới.

**Cần nắm:** cách điền bit, chiều rộng `int`/`long`, quy tắc mask số bit cần dịch, nâng kiểu số nguyên nhỏ, phép gán dịch kết hợp, ứng dụng trích xuất bit và khác biệt so với phép chia số nguyên.

## 2. Quan sát bit qua hệ thập lục phân

Trong Java, `int` dùng **32 bit** và `long` dùng **64 bit**, số âm biểu diễn theo **bù hai** (*two's complement*). Với `int n = -8`:

~~~text
n        = 11111111 11111111 11111111 11111000  (0xFFFFFFF8)
n >> 2   = 11111111 11111111 11111111 11111110  (0xFFFFFFFE = -2)
n >>> 2  = 00111111 11111111 11111111 11111110  (0x3FFFFFFE = 1073741822)
~~~

Bốn điểm dễ kiểm chứng:

1. Bit trái nhất của `-8` là **1**.
2. `-8 >> 2` điền thêm **hai bit 1** bên trái.
3. `-8 >>> 2` điền thêm **hai bit 0** bên trái.
4. Kết quả `>>>` vẫn là **kiểu `int`**, chỉ khác giá trị bit. Không có kiểu nguyên thủy `uint` trong Java.

In dạng hex bằng JDK:

~~~java
System.out.println(Integer.toHexString(-8));        // fffffff8
System.out.println(Integer.toHexString(-8 >> 2));   // fffffffe
System.out.println(Integer.toHexString(-8 >>> 2));  // 3ffffffe
~~~

`Integer.toHexString` biểu diễn bit của `int` ở dạng hex không dấu, rất hữu ích để kiểm tra thao tác bit.

## 3. Với số không âm, `>>` và `>>>` thường giống nhau

~~~java
int number = 24;

System.out.println(number >> 2);  // 6
System.out.println(number >>> 2); // 6
~~~

Vì bit cao nhất của số `int` không âm bằng 0, `>>` điền bit 0 giống `>>>`.

| Giá trị `int` | `>> 2` | `>>> 2` | Nhận xét |
|---:|---:|---:|---|
| `24` | `6` | `6` | Cùng bit điền 0 |
| `8` | `2` | `2` | Cùng kết quả |
| `0` | `0` | `0` | Zero giữ nguyên |
| `-8` | `-2` | `1073741822` | Khác vì bit dấu |
| `-1` | `-1` | `1073741823` | Dịch 2 bit |

**Giới hạn cách hiểu:** “giống nhau” ở đây là với số `int`/`long` **không âm**, khi dùng cùng khoảng dịch. Với số âm và khoảng dịch dương hữu hiệu, hai toán tử có cách điền bit khác nhau.

## 4. `>>`: dịch phải có dấu

Quy tắc `x >> n` điền bit cao mới bằng bit dấu của `x` sau khi áp dụng quy tắc kiểu. Đối với số âm, bit dấu luôn là 1 sau dịch; đối với số không âm, bit dấu là 0.

~~~java
System.out.println(-8 >> 1); // -4
System.out.println(-8 >> 2); // -2
System.out.println(-1 >> 5); // -1
~~~

Tính chất hay dùng: với `int`/`long` và khoảng dịch hữu hiệu `n`, `x >> n` tương ứng với chia cho `2^n` và **lấy phần nguyên xuống** (*floor*) về phía âm vô cực. Với số âm lẻ, điều này **khác phép chia nguyên `/`**, vốn cắt thương về 0:

~~~java
System.out.println(-7 / 2);           // -3
System.out.println(-7 >> 1);          // -4
System.out.println(Math.floorDiv(-7, 2)); // -4
~~~

**Không dùng `x >> 1` thay cho `x / 2` nếu cần thương cắt về 0 với số âm.** Với số nguyên không âm, cả hai có thể cùng kết quả khi số chia là lũy thừa 2.

## 5. `>>>`: dịch phải không dấu (logic)

`x >>> n` luôn điền bit 0 bên trái. Với `int` âm, kết quả thường trở thành một `int` không âm khi dịch ít nhất một bit:

~~~java
int negative = -8;
System.out.println(negative >>> 1); // 2147483644
System.out.println(negative >>> 2); // 1073741822
~~~

Ví dụ `-1` có 32 bit đều bằng 1:

~~~java
System.out.println(-1 >>> 1); // 2147483647
~~~

`>>>` hữu ích khi muốn coi mẫu bit như một **giá trị không dấu** để dịch, ví dụ tách các bit dữ liệu từ một `int`. Nó không đổi loại biến sang một kiểu unsigned và không cho phép biểu diễn toàn bộ miền unsigned 32 bit thành `int` dương **mà không có xử lý bổ sung**.

Java 17 hỗ trợ một số API diễn giải `int` dưới dạng unsigned, như `Integer.toUnsignedLong`, `Integer.compareUnsigned` và `Integer.divideUnsigned`.

~~~java
System.out.println(Integer.toUnsignedLong(-8)); // 4294967288
System.out.println(Integer.divideUnsigned(-8, 4)); // 1073741822
~~~

Trong trường hợp chia unsigned cho `4 = 2^2`, `Integer.divideUnsigned(-8, 4)` bằng `-8 >>> 2`. Khi mẫu không phải lũy thừa hai, không thay phép chia bằng shift một cách máy móc.

## 6. `int` và `long`: chiều rộng khác nhau

| Kiểu toán hạng bên trái sau nâng kiểu | Chiều rộng phép dịch | Số bit dùng xác định khoảng dịch |
|---|---:|---|
| `int` | 32 bit | **5 bit thấp** của khoảng dịch |
| `long` | 64 bit | **6 bit thấp** của khoảng dịch |

~~~java
int a = -8;
long b = -8L;

System.out.println(a >>> 2); // 1073741822
System.out.println(b >>> 2); // 4611686018427387902
~~~

Hai biểu thức khác nhau vì với `long` có **64 bit**, việc điền 0 cho hai bit cao để lại 62 bit biểu diễn kết quả.

~~~java
System.out.println(Long.toHexString(-8L >> 2));  // fffffffffffffffe
System.out.println(Long.toHexString(-8L >>> 2)); // 3ffffffffffffffe
~~~

**Hãy dùng literal `L` khi muốn phép dịch 64 bit.** Không nên tính trên `int` rồi mới gán sang `long` và kỳ vọng kết quả sẽ giống dịch `long` ngay từ đầu.

## 7. Khoảng dịch được mask trước khi tính

Cả `>>` và `>>>` đều dùng **5 bit thấp** của số lượng dịch nếu toán hạng trái là `int`, hoặc **6 bit thấp** nếu là `long`. Ví dụ:

~~~java
System.out.println(-8 >>> 32);   // -8: 32 & 31 = 0.
System.out.println(-8 >>> 34);   // 1073741822: dịch hiệu lực 2 bit.
System.out.println(-8L >>> 66);  // 4611686018427387902: 66 & 63 = 2.
System.out.println(1 >> -1);     // 0: -1 & 31 = 31.
~~~

Các khoảng dịch âm hoặc vượt độ rộng không tự ném ngoại lệ. Nếu số lượng dịch là dữ liệu do người dùng cung cấp, hãy kiểm tra giới hạn trước khi dịch, bởi các bit bị mask có thể khiến đầu vào sai tạo kết quả có vẻ hợp lệ. Bài về giới hạn khoảng dịch phân tích đầy đủ quy tắc này; ở đây điều cần quan sát là **cách `>>` và `>>>` điền bit vẫn khác nhau khi khoảng dịch hiệu lực giống nhau**.

## 8. `byte`, `short`, `char` được nâng thành `int` trước khi dịch

Toán tử dịch áp dụng *unary numeric promotion* cho **từng toán hạng**; kiểu kết quả của biểu thức dịch là kiểu toán hạng **bên trái sau nâng kiểu**. Khác với cộng số, toán hạng phải **không làm toán hạng trái trở thành `long`** chỉ vì số dịch thuộc kiểu `long`.

~~~java
byte small = -8;
int result = small >>> 2;

System.out.println(result); // 1073741822
~~~

`small` được **sign-extend từ byte lên int** trước, thành `0xFFFFFFF8`; sau đó `>>>` dịch trên 32 bit. Không phải Java đang dịch trực tiếp trên 8 bit rồi tạo một số không dấu 8 bit.

Với `char`, vì `char` lưu **UTF-16 code unit không dấu**, chuyển lên `int` có giá trị từ 0 tới 65535, nên bit dấu int vẫn bằng 0:

~~~java
char codeUnit = '\uFF80';
System.out.println(codeUnit >> 4);  // 4088
System.out.println(codeUnit >>> 4); // 4088
~~~

Với `short` âm, kết quả cũng chịu sign-extension sang int trước khi dịch.

### `>>>=`: gán dịch kết hợp có thu hẹp ngầm

~~~java
byte small = -8;
small >>>= 2;
System.out.println(small); // -2
~~~

Mô hình cơ bản của `small >>>= 2` là dịch trên `int`, rồi **thu hẹp** kết quả về `byte` (giữ 8 bit thấp). Vì thế kết quả gán lại là -2, trong khi biểu thức `small >>> 2` gán vào `int` cho 1073741822.

~~~java
// small = small >>> 2; // LỖI COMPILE: biểu thức bên phải là int
small = (byte) (small >>> 2); // Có cast tường minh, nhưng xem lại giá trị hiện tại của small
~~~

Quy tắc `op=` còn có điểm đặc biệt: **vế trái chỉ được đánh giá một lần**. Không nên thay máy móc các compound assignment có chỉ số mảng hoặc method side effect bằng dạng gán dài.

## 9. Dịch bit không phải luôn là phép chia số học

| Biểu thức | Với `x = -7` | Giải thích |
|---|---:|---|
| `x / 2` | `-3` | Chia nguyên, cắt về 0 |
| `x >> 1` | `-4` | Dịch có dấu, tương ứng floor |
| `x >>> 1` | `2147483644` | Dịch 32 bit với điền zero |

Việc dùng `>>>` thay cho phép chia số nguyên **đặc biệt nguy hiểm** nếu dữ liệu có thể âm: nó diễn giải bit như unsigned, cho kết quả rất khác.

Với số nguyên **không âm**, `x >> n` và `x >>> n` thường tương ứng với thương của phép chia cho `2^n` khi `n` nằm trong khoảng hợp lý. Nhưng **ưu tiên `/` khi code cần diễn đạt phép chia**: dễ đọc hơn và không khiến người bảo trì hiểu sai về dấu hay khoảng dịch.

## 10. Dùng `>>>` để trích xuất trường bit

Giả sử một `int` đóng gói 4 byte:

~~~text
0x12 34 AB CD
~~~

Muốn lấy byte thứ hai từ phải (`0xAB`):

~~~java
int packed = 0x1234ABCD;
int extracted = (packed >>> 8) & 0xFF;

System.out.println(extracted); // 171 (0xAB)
~~~

Diễn biến:

1. `packed >>> 8` dịch bit để đưa `0xAB` vào vùng 8 bit thấp.
2. `& 0xFF` giữ **8 bit thấp**, xóa các bit khác.
3. Kết quả là 171, giá trị unsigned của byte `0xAB`.

Tương tự, tách **bit dấu** từ một `int`:

~~~java
int signed = Integer.MIN_VALUE;
int highBit = signed >>> 31;
System.out.println(highBit); // 1
~~~

Nếu dùng `signed >> 31`, kết quả là **-1** vì `>>` điền toàn 1 ở bit trái. Đây là lý do `>>>` thường được chọn khi xử lý cấu trúc bit/flags.

**Chú ý:** trích xuất bit không tự xác nhận dữ liệu đầu vào hợp lệ. Với protocol, hãy xác nhận độ dài, kiểu dữ liệu và vị trí trường bit trước khi dịch/mask.

## 11. Ưu tiên toán tử và dấu ngoặc

`>>` và `>>>` thuộc nhóm **toán tử dịch**; chúng có độ ưu tiên thấp hơn `+`/`-`, nhưng cao hơn nhiều toán tử so sánh/bitwise boolean. Đặt ngoặc để thể hiện rõ ý định:

~~~java
int flags = 0x80000000;
boolean topBitSet = (flags >>> 31) == 1;
System.out.println(topBitSet); // true
~~~

Với mask:

~~~java
int byteValue = (packed >>> 8) & 0xFF;
~~~

Dấu ngoặc quanh phép dịch làm rõ việc **dịch trước, mask sau**, dù phép dịch có ưu tiên cao hơn `&`.

Đừng nhầm `>>`/`>>>` trong **biểu thức số học** với ký tự `>` xuất hiện trong mã generic như `Map<String, List<Integer>>`: đây là hai ngữ cảnh cú pháp khác nhau.

## 12. Lỗi phổ biến và cách xử lý

| Ngộ nhận/lỗi | Vì sao sai | Cách đúng |
|---|---|---|
| `>>` và `>>>` là như nhau | Khác cách điền bit cao khi số âm | Chọn theo mục tiêu signed/bitwise |
| `-8 >>> 2` là `-2` | `>>>` điền 0, ra 1073741822 | `-8 >> 2` nếu muốn giữ dấu |
| `>>> ` làm int thành unsigned primitive | Java không có kiểu `uint` nguyên thủy | Dùng các API unsigned nếu cần |
| `-7 >> 1` bằng `-7 / 2` | Dịch có dấu làm tròn xuống, chia nguyên cắt về 0 | Dùng `/` nếu cần cắt về 0 |
| `int x; x >>> 32` cho 0 | Khoảng dịch int được mask 5 bit | Validate khoảng dịch nếu cần |
| `long x` dùng phép dịch 32 bit | long dùng 64 bit | Kiểm tra kiểu toán hạng trái |
| `byte >>> 2` dịch trên 8 bit | byte được nâng thành int 32 bit | Cân nhắc sign-extension |
| `byte b; b >>>= 2` trả một byte unsigned lớn | Compound assignment thu hẹp về byte | Xem giá trị int trung gian |
| `x >>> 2` có cùng nghĩa với unsigned `x / 4` ở mọi trường hợp | Chỉ đúng khi xử lý bit unsigned 32/64 và mẫu lũy thừa hai | Dùng `divideUnsigned` khi phù hợp |
| Dùng `>>>` để kiểm tra số âm | `>>>` làm đổi bit dấu của kết quả khi dịch | Dùng `x < 0` khi ý định là so dấu |
| Viết `flags >>> 31 == 1` không chú giải | Dễ hiểu sai precedence | Viết `(flags >>> 31) == 1` |
| Giả định shift luôn nhanh hơn phép chia | JVM/JIT có tối ưu riêng | Ưu tiên ngữ nghĩa rõ, benchmark nếu cần |
| Dùng khoảng dịch âm như một tính năng nghiệp vụ | Java mask bit, có thể gây bất ngờ | Validate `n >= 0` và giới hạn phù hợp |

## 13. Chương trình Java 17 chạy độc lập

Tạo đúng file **`SignedUnsignedShiftDemo.java`**:

~~~java
public final class SignedUnsignedShiftDemo {
    private SignedUnsignedShiftDemo() {}

    static void showInt(String label, int value) {
        System.out.println(label + "=" + value
                + ",hex=" + Integer.toHexString(value));
    }

    public static void main(String[] args) {
        showInt("positive >>2", 8 >> 2);
        showInt("positive >>>2", 8 >>> 2);

        showInt("negative original", -8);
        showInt("negative >>2", -8 >> 2);
        showInt("negative >>>2", -8 >>> 2);
        showInt("negative >>>1", -8 >>> 1);
        showInt("all ones >>>1", -1 >>> 1);

        showInt("MIN >>1", Integer.MIN_VALUE >> 1);
        showInt("MIN >>>1", Integer.MIN_VALUE >>> 1);

        long wide = -8L;
        System.out.println("long >>2=" + (wide >> 2));
        System.out.println("long >>>2=" + (wide >>> 2));
        System.out.println("long >>2 hex="
                + Long.toHexString(wide >> 2));
        System.out.println("long >>>2 hex="
                + Long.toHexString(wide >>> 2));

        showInt("int >>>32", -8 >>> 32);
        showInt("int >>>34", -8 >>> 34);
        System.out.println("long >>>66=" + (wide >>> 66));
        System.out.println("negative shift=" + (1 >> -1));

        byte small = -8;
        showInt("byte >>>2 promoted", small >>> 2);
        small >>>= 2;
        System.out.println("byte >>>=2=" + small);

        char codeUnit = '\uFF80';
        System.out.println("char >>4=" + (codeUnit >> 4));
        System.out.println("char >>>4=" + (codeUnit >>> 4));

        System.out.println("negative division=" + (-7 / 2));
        System.out.println("negative >>1=" + (-7 >> 1));
        System.out.println("negative >>>1=" + (-7 >>> 1));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 2));

        System.out.println("unsigned long view="
                + Integer.toUnsignedLong(-8));
        System.out.println("unsigned /4="
                + Integer.divideUnsigned(-8, 4));

        int packed = 0x1234ABCD;
        int extracted = (packed >>> 8) & 0xFF;
        System.out.println("extracted byte=" + extracted);

        int sign = Integer.MIN_VALUE;
        System.out.println("top bit unsigned=" + (sign >>> 31));
        System.out.println("top bit signed=" + (sign >> 31));
        System.out.println("top bit set=" + ((sign >>> 31) == 1));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal đang mở tại thư mục chứa file; không cần Maven, Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SignedUnsignedShiftDemo.java
java -cp . SignedUnsignedShiftDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SignedUnsignedShiftDemo.java
java -cp . SignedUnsignedShiftDemo
~~~

### Exact expected stdout

~~~text
positive >>2=2,hex=2
positive >>>2=2,hex=2
negative original=-8,hex=fffffff8
negative >>2=-2,hex=fffffffe
negative >>>2=1073741822,hex=3ffffffe
negative >>>1=2147483644,hex=7ffffffc
all ones >>>1=2147483647,hex=7fffffff
MIN >>1=-1073741824,hex=c0000000
MIN >>>1=1073741824,hex=40000000
long >>2=-2
long >>>2=4611686018427387902
long >>2 hex=fffffffffffffffe
long >>>2 hex=3ffffffffffffffe
int >>>32=-8,hex=fffffff8
int >>>34=1073741822,hex=3ffffffe
long >>>66=4611686018427387902
negative shift=0
byte >>>2 promoted=1073741822,hex=3ffffffe
byte >>>=2=-2
char >>4=4088
char >>>4=4088
negative division=-3
negative >>1=-4
negative >>>1=2147483644
floorDiv=-4
unsigned long view=4294967288
unsigned /4=1073741822
extracted byte=171
top bit unsigned=1
top bit signed=-1
top bit set=true
~~~

### Cách đối chiếu kết quả

1. **Giá trị không âm:** `8 >> 2` và `8 >>> 2` đều bằng 2.
2. **Giá trị âm:** `-8 >> 2` còn dấu âm (hex `fffffffe`), nhưng `-8 >>> 2` điền 0 (hex `3ffffffe`).
3. **Bit dấu cao:** `MIN_VALUE >> 1` điền bit 1; `MIN_VALUE >>> 1` điền 0.
4. **Chiều rộng:** phép dịch `long` có kết quả khác `int`; `Long.toHexString` cho 16 chữ số hex khi cần.
5. **Mask khoảng dịch:** `int >>> 32` tương ứng dịch 0; `int >>> 34` dịch 2; `long >>> 66` cũng dịch 2.
6. **Nâng kiểu:** `byte >>> 2` được tính trên int; `byte >>>= 2` chuyển kết quả trở lại byte.
7. **Phép chia:** `-7 / 2` là -3, khác `-7 >> 1` là -4.
8. **Unsigned API:** `Integer.toUnsignedLong(-8)` cho 4294967288, còn chia unsigned cho 4 cho 1073741822.
9. **Trích xuất bit:** dịch `packed` rồi `& 0xFF` lấy `0xAB = 171`; bit cao nhất của `MIN_VALUE` được tách thành 1 bằng `>>>`.

## 14. Bài tập có đáp án

### Bài A — âm với hai cách dịch

~~~java
int x = -16;
System.out.println(x >> 2);
System.out.println(x >>> 2);
~~~

**Đáp án:**

~~~text
-4
1073741820
~~~

Vì `-16` có hex `0xfffffff0`; dịch logic hai bit tạo `0x3ffffffc`.

### Bài B — trích xuất một byte

Cho `int packed = 0x12AB34CD;`, lấy byte ở vị trí bit 16–23 (`0xAB`) dưới dạng số từ 0 tới 255.

**Đáp án:**

~~~java
int extracted = (packed >>> 16) & 0xFF;
System.out.println(extracted); // 171
~~~

### Bài C — tác động của mask

~~~java
System.out.println(-1 >>> 32);
System.out.println(-1 >>> 33);
~~~

**Đáp án:**

~~~text
-1
2147483647
~~~

Trên `int`, số dịch 32 trở thành 0; 33 trở thành 1.

### Bài D — byte được nâng kiểu

~~~java
byte b = -1;
int result = b >>> 1;
System.out.println(result);
~~~

**Đáp án:** `2147483647`. Byte `-1` được nâng có dấu thành int `0xffffffff`, rồi `>>> 1` thành `0x7fffffff`.

### Bài E — dịch và chia nguyên

~~~java
int x = -9;
System.out.println(x / 2);
System.out.println(x >> 1);
~~~

**Đáp án:**

~~~text
-4
-5
~~~

Phép chia nguyên cắt về 0, còn dịch phải có dấu với 1 bit tương ứng floor.

### Bài F — chọn toán tử

Muốn lấy bit dấu cao nhất của `int flags` dưới dạng **0 hoặc 1**, dùng biểu thức nào?

**Đáp án:** `(flags >>> 31) & 1` hoặc đơn giản `flags >>> 31`. Với `int`, dịch logic 31 bit chỉ để lại bit cao ban đầu ở vị trí thấp nhất; kết quả là 0 hoặc 1. `flags >> 31` lại có thể trả 0 hoặc -1.

## 15. Checklist và kết luận

- [ ] Hiểu `>>` điền bit dấu, `>>>` điền zero ở bên trái.
- [ ] Biết hai toán tử cho cùng kết quả với số nguyên không âm và cùng khoảng dịch.
- [ ] Tự giải thích được `-8 >> 2 = -2`, `-8 >>> 2 = 1073741822`.
- [ ] Nhớ `int` là 32 bit, `long` là 64 bit.
- [ ] Biết `int` mask 5 bit khoảng dịch, `long` mask 6 bit.
- [ ] Biết `byte`/`short`/`char` được nâng thành int trước khi dịch.
- [ ] Phân biệt biểu thức `byte >>> 2` kiểu int với `byte >>>= 2` gán lại byte.
- [ ] Không nhầm `>>` với phép chia số nguyên cắt về 0 khi số âm.
- [ ] Biết `>>>` có ích khi trích xuất bit và coi mẫu bit như unsigned.
- [ ] Hiểu `>>>` không tạo kiểu primitive unsigned mới.
- [ ] Dùng ngoặc khi kết hợp dịch và mask; xét sign-extension trước khi chuyển kiểu.
- [ ] Validate số bit dịch nếu nghiệp vụ không cho phép giá trị âm hoặc quá chiều rộng.
- [ ] Chạy `SignedUnsignedShiftDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** `>>` giữ dấu bằng cách điền bit dấu; `>>>` dịch logic bằng cách điền bit 0. Sự khác biệt nổi bật ở **số âm**, ngoài ra còn cần chú ý **32/64 bit, mask khoảng dịch, numeric promotion và compound assignment**. Dùng `>>>` để thao tác mẫu bit/unsigned một cách chủ đích; dùng toán tử chia khi mục tiêu thực sự là số học, đặc biệt với số âm.