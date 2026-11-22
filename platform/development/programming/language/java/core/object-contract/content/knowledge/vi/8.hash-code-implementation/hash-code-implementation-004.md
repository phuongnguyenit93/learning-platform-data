# Dùng phương thức `hashCode()` của các lớp bao cho kiểu nguyên thủy

## 1. Mục tiêu

Khi tự cài đặt `hashCode()` cho một lớp Java, ta cần chuyển từng trường tham gia quan hệ bằng nhau thành giá trị băm kiểu `int`, rồi kết hợp các giá trị ấy theo một quy tắc ổn định. Với trường có kiểu nguyên thủy (`primitive`), Java cung cấp ngay các phương thức `hashCode(primitive)` **tĩnh** trên lớp bao tương ứng, ví dụ `Integer.hashCode(int)` hoặc `Double.hashCode(double)`.

Sau bài này, bạn cần:

- Biết đủ tám cặp primitive và wrapper; gọi đúng phương thức static mà không cần đóng hộp thủ công.
- Hiểu vì sao kết quả `hashCode` của từng loại có thể khác cách ép kiểu thô sang `int`, đặc biệt `long`, `float` và `double`.
- Cài đặt `equals()` và `hashCode()` nhất quán khi lớp có nhiều trường primitive.
- Tránh nhầm lẫn giữa hash của **một giá trị**, hash kết hợp của **một đối tượng nhiều trường**, và danh tính đối tượng.
- Biết xử lý `NaN`, `+0.0` và `-0.0` để không phá hợp đồng `equals`/`hashCode`.

## 2. Phương thức static của tám lớp bao

Tất cả lớp dưới đây thuộc `java.lang`, không cần `import`. Mỗi phương thức nhận trực tiếp một primitive và trả về `int`:

| Kiểu nguyên thủy | Lớp bao | Cách lấy hash từ primitive | Quy tắc chính |
| --- | --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.hashCode(value)` | `true → 1231`, `false → 1237`. |
| `byte` | `Byte` | `Byte.hashCode(value)` | Trả về trị số `byte` dưới dạng `int`. |
| `short` | `Short` | `Short.hashCode(value)` | Trả về trị số `short` dưới dạng `int`. |
| `char` | `Character` | `Character.hashCode(value)` | Trả về mã số của đơn vị mã UTF-16 kiểu `char`. |
| `int` | `Integer` | `Integer.hashCode(value)` | Trả về chính giá trị `int`. |
| `long` | `Long` | `Long.hashCode(value)` | Trộn 32 bit cao và 32 bit thấp. |
| `float` | `Float` | `Float.hashCode(value)` | Dựa trên `Float.floatToIntBits(value)`. |
| `double` | `Double` | `Double.hashCode(value)` | Dựa trên bit của `Double.doubleToLongBits(value)`, rồi trộn hai nửa 32 bit. |

Ví dụ gọi trực tiếp:

```java
int ageHash = Integer.hashCode(25);
int enabledHash = Boolean.hashCode(true);
int idHash = Long.hashCode(5_000_000_000L);
int ratioHash = Float.hashCode(1.5f);
int amountHash = Double.hashCode(1.5);
```

Đây là đoạn minh họa, không phải chương trình độc lập. Các phương thức `hashCode(primitive)` tĩnh đã có từ Java 8, do đó dùng được trong Java 17+.

### Static `hashCode(primitive)` và instance `hashCode()`

Lớp bao còn có phương thức `hashCode()` **của đối tượng**:

```java
int a = Integer.hashCode(42);        // static: tham số int
int b = Integer.valueOf(42).hashCode(); // instance: đối tượng Integer
// a == b
```

Hai cách cho cùng kết quả đối với giá trị tương ứng. Tuy nhiên, khi dữ liệu gốc đã là primitive, hãy ưu tiên lời gọi static: diễn đạt ý định rõ, không cần tạo một biến wrapper, tránh yêu cầu đóng hộp chỉ để gọi instance method. Không khẳng định rằng mỗi lần autoboxing chắc chắn cấp phát đối tượng: JVM có thể dùng cache hoặc tối ưu hóa.

Một biến tham chiếu wrapper có thể `null`; gọi `wrapper.hashCode()` trực tiếp khi null sẽ ném `NullPointerException`. Primitive không bao giờ null, vì vậy `Integer.hashCode(int)` không gặp trường hợp đó.

## 3. Hiểu cơ chế từng nhóm kiểu

### 3.1. `boolean`, `byte`, `short`, `char` và `int`

`Boolean.hashCode(true)` trả `1231`; `Boolean.hashCode(false)` trả `1237`. Đây là các hằng số do Java định nghĩa, **không phải** `1` và `0`.

`Byte.hashCode(byte)` và `Short.hashCode(short)` trả về giá trị số sau khi chuyển sang `int`. Với giá trị âm, dấu âm được bảo toàn. `Character.hashCode(char)` trả về mã số của một `char` (0–65535), vốn là **một đơn vị mã UTF-16**, không nhất thiết đại diện cho toàn bộ một ký tự Unicode nằm ngoài Basic Multilingual Plane. `Integer.hashCode(int)` trả về đúng giá trị `int` đầu vào.

Ví dụ:

```java
Boolean.hashCode(true);          // 1231
Boolean.hashCode(false);         // 1237
Byte.hashCode((byte) -5);        // -5
Short.hashCode((short) 300);     // 300
Character.hashCode('A');        // 65
Integer.hashCode(42);           // 42
```

Các con số này là giá trị hash của từng primitive; **không đảm bảo khác nhau giữa mọi đầu vào hoặc mọi kiểu dữ liệu**. Các đối tượng phức hợp phải kết hợp hash theo những trường tạo nên giá trị của chúng.

### 3.2. `long`: không ép kiểu mất 32 bit cao

`long` có 64 bit, còn `hashCode()` phải trả `int` có 32 bit. Công thức chuẩn của `Long.hashCode(long value)` tương đương:

```java
(int) (value ^ (value >>> 32))
```

Đây là biểu thức minh họa: XOR 32 bit cao với 32 bit thấp, rồi lấy 32 bit kết quả. Khi ép thẳng `(int) value`, 32 bit cao bị bỏ đi; vì vậy hai giá trị `long` chỉ khác nhau ở phần cao có thể bị trùng hash một cách không cần thiết.

Ví dụ:

```java
long id = 0x1_0000_0002L;
int lowOnly = (int) id;       // 2
int mixed = Long.hashCode(id); // 3: 1 XOR 2
```

`Long.hashCode` vẫn có thể xảy ra collision, vì không thể ánh xạ không trùng mọi giá trị 64 bit vào miền 32 bit. Mục tiêu là tạo kết quả băm xác định và phù hợp với hợp đồng, không phải tạo mã định danh duy nhất.

### 3.3. `float` và `double`: dùng bit chuẩn hóa của kiểu dấu phẩy động

Không dùng `(int) someFloat` hay `(int) someDouble` làm phương án mặc định. Ép kiểu số thực sang `int` chuyển đổi trị số, có thể mất phần thập phân và không giữ các phân biệt quan trọng trong hợp đồng của wrapper.

Về ngữ nghĩa, các cách tính là:

```java
int floatHash = Float.floatToIntBits(valueFloat);

// Hành vi tương đương Double.hashCode(valueDouble):
long bits = Double.doubleToLongBits(valueDouble);
int doubleHash = (int) (bits ^ (bits >>> 32));
```

Đây là đoạn minh họa công thức; giả sử hai biến `valueFloat` và `valueDouble` đã được khai báo đúng kiểu.

`Float.floatToIntBits` và `Double.doubleToLongBits` **quy các biểu diễn NaN khác nhau về một biểu diễn bit NaN chuẩn** cho mục đích so sánh/hash. Chúng vẫn phân biệt dấu của zero:

- `Float.hashCode(+0.0f)` khác `Float.hashCode(-0.0f)`.
- `Double.hashCode(+0.0)` khác `Double.hashCode(-0.0)`.
- Các payload NaN khác nhau được chuẩn hóa về cùng bit pattern, nên có cùng hash theo phương thức wrapper tương ứng.

Điểm này đặc biệt quan trọng khi viết `equals()`:

- Toán tử primitive `0.0 == -0.0` là `true`; `Double.compare(0.0, -0.0)` **khác 0**.
- Toán tử primitive `Double.NaN == Double.NaN` là `false`; `Double.compare(Double.NaN, Double.NaN)` là `0`.
- Nếu `equals()` của lớp dùng `==` để so trường `double` nhưng `hashCode()` dùng `Double.hashCode`, hai đối tượng chứa `+0.0` và `-0.0` có thể được `equals` coi bằng nhau nhưng có hash khác nhau, **vi phạm hợp đồng**.

Với ý định dùng ngữ nghĩa wrapper, so `double` bằng `Double.compare(a, b) == 0` và so `float` bằng `Float.compare(a, b) == 0`, đồng thời dùng `Double.hashCode`/`Float.hashCode`. Nếu bài toán cần một quan hệ bằng nhau khác (chẳng hạn coi `+0.0` và `-0.0` bằng nhau), hãy **chuẩn hóa nhất quán cả trong `equals` và `hashCode`**. Không tự dùng so sánh sai số `epsilon` cho `equals` vì “gần bằng” thông thường có thể không bắc cầu.

## 4. Từ hash từng trường đến hash của đối tượng

Một lớp có nhiều trường cần tạo hash tổng hợp. Một mẫu phổ biến:

```java
int result = 1;
result = 31 * result + Integer.hashCode(count);
result = 31 * result + Long.hashCode(id);
result = 31 * result + Boolean.hashCode(active);
```

`31` là hệ số thường gặp trong Java, **không phải yêu cầu bắt buộc của hợp đồng**. Phép nhân/cộng `int` có thể tràn số; Java thực hiện tràn `int` theo quy tắc 32 bit và đó là điều bình thường trong một phép băm. Cần giữ **đúng thứ tự và cùng tập trường** mỗi lần tính.

Quan trọng hơn công thức cụ thể là hợp đồng của `Object.hashCode()`:

> Nếu `a.equals(b)` trả `true`, thì `a.hashCode() == b.hashCode()` bắt buộc là `true`.

Chiều ngược lại không bắt buộc: hai đối tượng không bằng nhau vẫn có thể chung hash. Hash cũng **không** chứng minh hai đối tượng là cùng một tham chiếu.

Các trường dùng để so `equals` phải tương ứng với các trường dùng để tính `hashCode`. Đừng thêm trường tạm, số lần truy cập, địa chỉ đối tượng hoặc timestamp thay đổi vào hash khi chúng không phải một phần giá trị bằng nhau. Với đối tượng làm khóa của `HashMap` hoặc phần tử của `HashSet`, tránh thay đổi trạng thái có ảnh hưởng đến hash sau khi thêm vào collection.

## 5. Chương trình Java 17+ đầy đủ

Tạo tệp `WrapperHashCodeDemo.java`. Ví dụ gọi cả tám wrapper và cài đặt `equals`/`hashCode` cho một value object có các trường primitive:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperHashCodeDemo {

    static final class ReadingKey {
        private final long deviceId;
        private final int sequence;
        private final boolean valid;
        private final double reading;

        ReadingKey(long deviceId, int sequence,
                   boolean valid, double reading) {
            this.deviceId = deviceId;
            this.sequence = sequence;
            this.valid = valid;
            this.reading = reading;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ReadingKey other)) {
                return false;
            }

            return deviceId == other.deviceId
                    && sequence == other.sequence
                    && valid == other.valid
                    && Double.compare(reading, other.reading) == 0;
        }

        @Override
        public int hashCode() {
            int result = Long.hashCode(deviceId);
            result = 31 * result + Integer.hashCode(sequence);
            result = 31 * result + Boolean.hashCode(valid);
            result = 31 * result + Double.hashCode(reading);
            return result;
        }
    }

    public static void main(String[] args) {
        System.out.println("boolean: " + Boolean.hashCode(true));
        System.out.println("byte: " + Byte.hashCode((byte) 7));
        System.out.println("short: " + Short.hashCode((short) 300));
        System.out.println("char: " + Character.hashCode('A'));
        System.out.println("int: " + Integer.hashCode(42));
        System.out.println("long: "
                + Long.hashCode(0x1_0000_0002L));
        System.out.println("float: " + Float.hashCode(1.5f));
        System.out.println("double: " + Double.hashCode(1.5));

        ReadingKey a = new ReadingKey(100L, 2, true, 1.5);
        ReadingKey b = new ReadingKey(100L, 2, true, 1.5);
        Set<ReadingKey> keys = new HashSet<>();
        keys.add(a);

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("set contains b: " + keys.contains(b));

        System.out.println("primitive zeros equal: "
                + (0.0 == -0.0));
        System.out.println("double zero hashes equal: "
                + (Double.hashCode(0.0)
                        == Double.hashCode(-0.0)));

        double otherNaN =
                Double.longBitsToDouble(0x7ff0000000000001L);
        System.out.println("NaNs compare equal: "
                + (Double.compare(Double.NaN, otherNaN) == 0));
        System.out.println("NaN hashes equal: "
                + (Double.hashCode(Double.NaN)
                        == Double.hashCode(otherNaN)));

        System.out.println("Objects.hash(42): "
                + Objects.hash(42));
    }
}
```

Biên dịch và chạy:

```bash
javac WrapperHashCodeDemo.java
java WrapperHashCodeDemo
```

Kết quả mong đợi trên Java 17+:

```text
boolean: 1231
byte: 7
short: 300
char: 65
int: 42
long: 3
float: 1069547520
double: 1073217536
a == b: false
a.equals(b): true
same hash: true
set contains b: true
primitive zeros equal: true
double zero hashes equal: false
NaNs compare equal: true
NaN hashes equal: true
Objects.hash(42): 73
```

### Giải thích kết quả

1. `Boolean` dùng hai hằng số hash; `Byte`/`Short`/`Character`/`Integer` phản ánh trị số theo quy tắc riêng từng kiểu.
2. `Long.hashCode(0x1_0000_0002L)` trộn phần cao `1` và phần thấp `2` thành `3`.
3. `Float.hashCode(1.5f)` và `Double.hashCode(1.5)` dựa trên mẫu bit chuẩn của số thực, không phải ép `1.5` thành số nguyên `1`.
4. `a` và `b` là hai đối tượng khác danh tính (`==` là `false`), nhưng mọi trường tham gia `equals` giống nhau, nên `a.equals(b)` là `true` và hash bằng nhau.
5. Vì hash và equality phù hợp, `HashSet` tìm được `b` dù chỉ thêm `a`.
6. Primitive `0.0 == -0.0` đúng, nhưng wrapper hash phân biệt dấu zero. Tương tự, `Double.compare` và `Double.hashCode` cùng coi mọi NaN là tương đương theo quy tắc bit chuẩn.
7. `Objects.hash(42)` trả `73`, khác `Integer.hashCode(42) == 42`, vì đây là **hàm kết hợp hash của danh sách tham số**, kể cả khi chỉ có một phần tử: với một tham số, phép hash mảng bắt đầu từ `1` rồi nhân `31` và cộng hash của phần tử.

## 6. So sánh với `Objects.hash` và `Objects.hashCode`

Có ba API dễ bị nhầm:

| Lời gọi | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `Integer.hashCode(value)` | Hash trực tiếp một `int` | Rõ ràng, không yêu cầu biến wrapper. |
| `Objects.hashCode(object)` | Gọi hash của **một đối tượng**, trả `0` nếu null | Primitive truyền vào sẽ cần boxing để thành `Object`. |
| `Objects.hash(a, b, ...)` | Kết hợp hash của nhiều đối tượng trong danh sách tham số | Dùng varargs/mảng, primitive phải boxing; kết quả một phần tử vẫn có thể khác hash riêng của phần tử. |

Ví dụ:

```java
Integer.valueOf(42).hashCode(); // 42
Integer.hashCode(42);           // 42
Objects.hashCode(42);           // 42 (boxing)
Objects.hash(42);               // 73 (một phần tử trong mảng)
Objects.hash(10, true, 1.5);    // hash tổng hợp các giá trị
```

Đoạn minh họa cần `import java.util.Objects;`.

`Objects.hash(...)` thuận tiện để viết ít mã, nhưng tạo mảng varargs và có thể boxing các primitive; với mã hash được tính rất thường xuyên hoặc nơi có yêu cầu hiệu năng nghiêm ngặt, cách kết hợp tường minh từ các phương thức static wrapper có thể giảm các đối tượng trung gian. JVM có thể tối ưu hóa cấp phát, do đó cần **benchmark đúng workload** trước khi kết luận về chênh lệch hiệu năng thực tế.

`Arrays.hashCode(primitiveArray)` lại là API riêng để tính hash theo các **phần tử của một mảng**. Đừng dùng `array.hashCode()` nếu `equals()` của lớp so nội dung mảng: mảng kế thừa cách hash theo danh tính của `Object`. Trong trường hợp đó, `Arrays.equals(a, b)` thường cần đi cùng `Arrays.hashCode(a)` (mảng lồng nhau có những API `deepEquals`/`deepHashCode` riêng).

## 7. Những lỗi cần tránh

### Lỗi 1: Ép `long` xuống `int`

```java
// Dễ bỏ mất ảnh hưởng của 32 bit cao:
int hash = (int) orderId;

// Bao gồm cả phần cao và thấp:
int hash = Long.hashCode(orderId);
```

### Lỗi 2: Ép `float` hoặc `double` xuống `int`

```java
// Mất phần thập phân và nhiều phân biệt của số thực:
int hash = (int) temperature;

// Hành vi theo wrapper:
int hash = Double.hashCode(temperature);
```

### Lỗi 3: `equals` so dấu phẩy động bằng `==` nhưng hash dùng wrapper

```java
// Không nhất quán khi dữ liệu có +0.0 và -0.0:
return this.value == other.value;

// Nếu hash dùng Double.hashCode(value), có thể chọn:
return Double.compare(this.value, other.value) == 0;
```

Các đoạn trên chỉ là **dòng minh họa bên trong phương thức của một lớp có trường `double value`**, không phải chương trình Java độc lập. Phải xác định trước quan hệ bằng nhau mong muốn; nếu yêu cầu coi hai zero bằng nhau, thay vì sử dụng `Double.compare`, hãy chuẩn hóa chúng cùng về `+0.0` cho cả so sánh và hash.

### Lỗi 4: Chỉ dùng hash của một trường trong khi `equals` xét nhiều trường

Điều này có thể **vẫn không vi phạm** hợp đồng `equals/hashCode` nếu hash đó bất biến cho mọi cặp được coi là bằng nhau, nhưng thường làm tăng collision và suy giảm hiệu năng collection. Hãy cân nhắc kết hợp đầy đủ các trường tạo nên equality. Chiều ngược lại nguy hiểm hơn: thêm trường **không tham gia `equals`** nhưng có thể khác nhau giữa hai đối tượng bằng nhau vào hash sẽ **vi phạm hợp đồng**.

### Lỗi 5: Nghĩ rằng “hash khác nhau” mới chứng minh hai đối tượng khác nhau

Nếu hai hash **khác nhau** thì hai đối tượng không thể bằng nhau theo một triển khai tuân thủ hợp đồng; tuy nhiên, hai hash **bằng nhau** chưa chứng minh hai đối tượng bằng nhau. `HashMap` và `HashSet` vẫn cần kiểm tra equality khi thích hợp.

### Lỗi 6: Hash dựa vào trạng thái có thể thay đổi

Nếu trường tham gia `equals/hashCode` bị sửa sau khi đối tượng vào `HashSet`, lời gọi `contains` có thể không tìm được phần tử cũ. Ưu tiên khóa bất biến với trường `final` và không để lộ thành phần mutable gây ảnh hưởng đến hash.

## 8. Checklist cài đặt `hashCode` cho lớp có primitive

1. Liệt kê đúng các trường quyết định quan hệ bằng nhau của lớp.
2. Với mỗi trường primitive, dùng `Boolean/Byte/Short/Character/Integer/Long/Float/Double.hashCode(value)` tương ứng.
3. Với trường là tham chiếu có thể null, dùng quy tắc null-safe, ví dụ `Objects.hashCode(field)`; với chuỗi, collection hoặc mảng, xem chính hợp đồng equality của chúng.
4. Kết hợp các giá trị hash theo thứ tự ổn định, ví dụ nhân `31` rồi cộng.
5. Kiểm tra hai đối tượng bằng nhau **luôn** có hash bằng nhau, kể cả các ca biên: số âm, `long` có bit cao, `NaN`, `+0.0`/`-0.0` và null (nếu được phép).
6. Kiểm thử việc thêm một key và tìm bằng một key khác có cùng giá trị trong `HashSet`/`HashMap`.
7. Nếu hash nằm trên đường nóng hiệu năng, đo trước khi quyết định dùng `Objects.hash` hay kết hợp thủ công.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao nên dùng `Long.hashCode(id)` thay vì `(int) id` cho trường `long`?

**Trả lời:** Vì `Long.hashCode` kết hợp cả hai nửa 32 bit. Ép kiểu xuống `int` chỉ giữ nửa thấp.

**Câu 2.** Với `double`, dùng `value == other.value` trong `equals` và `Double.hashCode(value)` trong `hashCode` có luôn an toàn không?

**Trả lời:** Không. Primitive `+0.0 == -0.0` trả `true` trong khi hai giá trị có hash wrapper khác nhau. Nếu chọn ngữ nghĩa wrapper, dùng `Double.compare(...) == 0` và `Double.hashCode(...)` nhất quán.

**Câu 3.** `Integer.hashCode(42)` và `Objects.hash(42)` có bằng nhau không?

**Trả lời:** Không. Trường hợp này lần lượt là `42` và `73` vì `Objects.hash` dùng thuật toán hash mảng chứa một phần tử.

**Câu 4.** Có thể dùng cùng một mã hash cho nhiều đối tượng khác nhau không?

**Trả lời:** Có. Collision được phép. Điều bắt buộc là những đối tượng được `equals` coi bằng nhau phải có mã hash bằng nhau.

**Câu 5.** Khi trường `boolean enabled` tham gia `equals`, cách hash trực tiếp là gì?

**Trả lời:** `Boolean.hashCode(enabled)`, trả về `1231` nếu `true` và `1237` nếu `false`.

**Ghi nhớ:** Các phương thức `hashCode(primitive)` **tĩnh trên lớp bao** cho phép chuyển primitive thành `int` theo quy tắc Java đã định nghĩa. Hãy kết hợp chúng nhất quán với các trường trong `equals()`, đặc biệt cẩn thận với `long`, `float` và `double`.