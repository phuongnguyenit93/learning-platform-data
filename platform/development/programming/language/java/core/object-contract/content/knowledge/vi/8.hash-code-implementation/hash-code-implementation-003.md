# Kết hợp hash của nhiều trường trong Java

## Mục tiêu

Khi đối tượng được xem là bằng nhau dựa trên **nhiều thuộc tính**, phương thức `hashCode()` cần tạo ra một mã băm phù hợp với định nghĩa bằng nhau đó. Bài học này giải thích cách phối hợp hash của nhiều trường, khi nào dùng `Objects.hash(...)`, khi nào tự kết hợp bằng phép nhân `31`, cách xử lý `null`, kiểu nguyên thủy, mảng, đối tượng lồng nhau và những lỗi làm `HashMap`/`HashSet` hoạt động sai kỳ vọng.

Sau bài học, bạn có thể:

- Chọn các trường cần kết hợp dựa vào `equals(Object)`.
- Viết `hashCode()` kết hợp nhiều trường bằng Java 17+ và kiểm tra tính nhất quán.
- Phân biệt cách băm trường thông thường với cách băm **nội dung mảng**.
- Hiểu vì sao thứ tự, tính ổn định và va chạm hash ảnh hưởng tới thiết kế, nhưng mã băm không phải định danh duy nhất.

## 1. Vì sao phải kết hợp nhiều trường?

Giả sử khóa nghiệp vụ `PersonKey` gồm ba trường:

```java
String region;
int number;
boolean active;
```

Nếu `equals` quyết định hai khóa bằng nhau khi **cả ba trường** tương ứng bằng nhau, ta muốn `hashCode` tính mã băm từ bộ giá trị đó. Một cách mô tả là:

```text
hash(PersonKey) = combine(
    hash(region),
    hash(number),
    hash(active)
)
```

Điều bắt buộc theo hợp đồng `Object` là:

> Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` cũng phải là `true`.

Chiều đảo **không bắt buộc**: hai đối tượng khác nhau vẫn có thể có cùng mã băm (**collision**). `hashCode()` trả về một số nguyên `int` 32-bit; số lượng giá trị hữu hạn khiến không thể kỳ vọng mã băm duy nhất cho mọi đối tượng khác nhau.

Có thể viết `hashCode()` trả về hằng số cho mọi đối tượng mà vẫn thỏa điều kiện “bằng nhau thì cùng hash”, nhưng điều này tạo nhiều va chạm và thường làm giảm hiệu quả của cấu trúc dữ liệu dựa trên hash. Vì vậy, lựa chọn thực hành tốt là kết hợp **các thành phần quyết định `equals`** để tạo phân bố hash hữu ích.

Hai câu hỏi phải trả lời trước khi viết hàm:

1. `equals` đang so sánh những trường nào?
2. Các trường ấy có ổn định trong thời gian đối tượng được sử dụng làm **khóa `HashMap`** hoặc **phần tử `HashSet`** hay không?

Không nên băm thêm một trường có thể khác nhau giữa hai đối tượng mà `equals` vẫn coi là bằng nhau: như vậy dễ tạo ra **hai hash khác nhau cho hai đối tượng bằng nhau**, vi phạm hợp đồng. Ngược lại, bỏ bớt trường khỏi hash chưa chắc làm sai hợp đồng, nhưng có thể tăng số lượng va chạm.

## 2. Cách nhanh và rõ ràng: `Objects.hash(...)`

Thư viện chuẩn có `java.util.Objects.hash(Object... values)`. Phương thức này nhận nhiều giá trị, tính hash kết hợp theo thứ tự đối số và hỗ trợ giá trị `null`. Các đối số nguyên thủy được **boxing** thành wrapper khi đi qua varargs kiểu `Object...`.

Ví dụ:

```java
@Override
public int hashCode() {
    return Objects.hash(region, number, active);
}
```

Cách này thường đủ tốt với value object thông thường khi số trường ít và đường thực thi không quá nhạy với chi phí cấp phát.

**Lưu ý:** `Objects.hash(region, number, active)` khác `Objects.hashCode(region)`:

- `Objects.hash(a, b, c)` **kết hợp nhiều giá trị** theo cách tương thích với `Arrays.hashCode(Object[])` cho mảng đối số varargs.
- `Objects.hashCode(x)` tính hash của **một đối tượng**; trả về `0` nếu `x == null`, nếu không trả về `x.hashCode()`.
- `Objects.hash(x)` với đúng một giá trị **không nhất thiết bằng** `Objects.hashCode(x)`: phép kết hợp varargs khởi đầu từ `1` và áp dụng công thức phối hợp, nên thường thêm bước `31`. Điều này không sai nếu cả `equals` và `hashCode` của lớp dùng nhất quán.

## 3. Cách thủ công: tích lũy hash theo hệ số 31

Một cách phổ biến là khởi tạo một số nguyên, sau đó lần lượt gộp từng trường:

```java
int result = 1;
result = 31 * result + hashOf(field1);
result = 31 * result + hashOf(field2);
result = 31 * result + hashOf(field3);
return result;
```

Trong đó `hashOf(...)` có thể là:

| Kiểu trường | Cách tính hash của một giá trị |
| --- | --- |
| `int` | `Integer.hashCode(value)` (hoặc chính giá trị `value`) |
| `long` | `Long.hashCode(value)` |
| `boolean` | `Boolean.hashCode(value)` |
| `byte`, `short`, `char` | `Byte.hashCode`, `Short.hashCode`, `Character.hashCode` |
| `float`, `double` | `Float.hashCode(value)`, `Double.hashCode(value)` |
| Đối tượng có thể `null` | `Objects.hashCode(value)` |
| Mảng nguyên thủy hoặc mảng đối tượng cần so theo phần tử | `Arrays.hashCode(array)`; xem mục 6 |
| Mảng đối tượng lồng nhau cần so sâu | `Arrays.deepHashCode(array)`; xem mục 6 |

Hệ số `31` là quy ước thực dụng đã được dùng rộng rãi trong Java. Nó giúp **thứ tự các giá trị** có ảnh hưởng đến kết quả, giảm bớt một số kiểu va chạm đơn giản so với phép cộng trần. Không có gì bảo đảm mọi tập giá trị khác nhau đều sinh hash khác nhau.

Khi phép nhân/cộng `int` tràn giới hạn, Java dùng phép toán `int` với kết quả theo 32-bit; overflow số nguyên trong cách phối hợp này là **bình thường** và vẫn có tính xác định. Không cần cố loại bỏ mọi overflow; đặc biệt không nên chuyển sang phép tính ngẫu nhiên làm mã băm thay đổi giữa các lần gọi cho cùng trạng thái đối tượng.

**Thứ tự trường:** Nếu bạn dùng `region → number → active` thì nên duy trì cùng thứ tự đó trong mỗi lần tính toán. Mã băm thay đổi khi đổi thứ tự trường vẫn có thể thỏa hợp đồng nếu triển khai nhất quán, nhưng thứ tự không ổn định giữa các lần tính là lỗi. Khi kiểm tra hai phiên bản công thức, chỉ có thể so số hash cụ thể khi cùng quy tắc và cùng thứ tự.

## 4. Ví dụ đầy đủ: `equals`, `Objects.hash` và cách thủ công

Tạo tệp **`MultiFieldHashDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MultiFieldHashDemo {
    static final class PersonKey {
        private final String region;
        private final int number;
        private final boolean active;

        PersonKey(String region, int number, boolean active) {
            this.region = region;
            this.number = number;
            this.active = active;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof PersonKey other)) {
                return false;
            }
            return number == other.number
                    && active == other.active
                    && Objects.equals(region, other.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(region, number, active);
        }

        int manualHashCode() {
            int result = 1;
            result = 31 * result + Objects.hashCode(region);
            result = 31 * result + Integer.hashCode(number);
            result = 31 * result + Boolean.hashCode(active);
            return result;
        }
    }

    public static void main(String[] args) {
        PersonKey first = new PersonKey("VN", 7, true);
        PersonKey equal = new PersonKey("VN", 7, true);
        PersonKey different = new PersonKey("VN", 7, false);

        System.out.println("first.equals(equal): "
                + first.equals(equal));
        System.out.println("same hash for equal keys: "
                + (first.hashCode() == equal.hashCode()));
        System.out.println("Objects.hash matches manual: "
                + (first.hashCode() == first.manualHashCode()));
        System.out.println("first.equals(different): "
                + first.equals(different));

        Set<PersonKey> keys = new HashSet<>();
        keys.add(first);
        System.out.println("set contains equal key: "
                + keys.contains(equal));

        PersonKey nullRegionA = new PersonKey(null, 7, true);
        PersonKey nullRegionB = new PersonKey(null, 7, true);
        System.out.println("null region keys equal: "
                + nullRegionA.equals(nullRegionB));
        System.out.println("null region hashes equal: "
                + (nullRegionA.hashCode() == nullRegionB.hashCode()));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac MultiFieldHashDemo.java
java MultiFieldHashDemo
```

**Đầu ra:**

```text
first.equals(equal): true
same hash for equal keys: true
Objects.hash matches manual: true
first.equals(different): false
set contains equal key: true
null region keys equal: true
null region hashes equal: true
```

Giải thích:

- `equals` kiểm tra **cùng ba trường** mà `hashCode` dùng để kết hợp. `Objects.equals(region, other.region)` xử lý được trường hợp một hoặc cả hai chuỗi `null`.
- `Objects.hash` vận dụng công thức tích lũy tương tự ví dụ thủ công: `result` ban đầu là `1`, với mỗi phần tử của varargs là `result = 31 * result + elementHash`. Ở đây thứ tự trường và hash từng thành phần trùng nhau nên kết quả bằng nhau.
- `Integer.hashCode` trả chính giá trị `int`, còn `Boolean.hashCode` trả hằng số xác định cho `true` và `false`. `Objects.hashCode(null)` trả `0`.
- Hai `PersonKey` bằng nhau có hash giống nhau. Nhờ đó, `HashSet.contains(equal)` có thể tìm ra phần tử được thêm từ một instance khác nhưng cùng giá trị.
- Ví dụ dùng trường `final` và kiểu thành phần bất biến (`String`, `int`, `boolean`), giúp giữ trạng thái khóa ổn định.

**Không hiểu nhầm:** dòng `first.equals(different): false` không tự bảo đảm hai hash tương ứng phải khác nhau. Việc khác nhau về giá trị có thể vẫn trùng hash; đó không phải vi phạm hợp đồng.

## 5. Vì sao cộng thẳng hay chỉ lấy một trường thường kém?

Một triển khai tự phát như:

```java
return x + y; // Ví dụ kém: không phân biệt (1, 2) với (2, 1).
```

có nhiều va chạm hiển nhiên: `(1, 2)` và `(2, 1)` cho cùng tổng. Một triển khai khác như `return region.hashCode();` bỏ qua `number` và `active`, khiến nhiều đối tượng khác nhau có chung mã băm. Bỏ trường không nhất thiết là **lỗi hợp đồng**, nhưng có thể làm giảm độ phân tán nếu những trường bị bỏ có giá trị phân biệt cao.

Phép nhân 31 phân biệt thứ tự tốt hơn trong nhiều tình huống:

```java
int result = 1;
result = 31 * result + x;
result = 31 * result + y;
return result;
```

Tuy nhiên **không tồn tại hàm băm `int` đảm bảo không va chạm cho mọi bộ giá trị có thể có**. Mục tiêu là một hàm nhanh, ổn định, có phân bố phù hợp, cùng thỏa hợp đồng `equals/hashCode`.

Với khóa ít trường, `Objects.hash(...)` thường dễ đọc và giảm nguy cơ quên trường. Với đoạn mã gọi hash rất thường xuyên, phối hợp thủ công có thể giảm chi phí cấp phát varargs và boxing; hãy dựa trên **đo đạc thực tế** trước khi tối ưu. Tránh tạo ra một thuật toán phức tạp chỉ để “đẹp” số hash.

## 6. Trường mảng: băm **nội dung** khác băm **tham chiếu**

Đây là bẫy quan trọng khi kết hợp nhiều trường.

Mảng trong Java là đối tượng. Nếu một lớp quyết định bằng nhau theo **nội dung các phần tử** (`Arrays.equals`), thì `hashCode` cũng phải dùng hàm hash nội dung tương ứng (`Arrays.hashCode`). Băm mảng bằng phương thức kế thừa từ `Object` về cơ bản dựa trên danh tính tham chiếu, không phản ánh các phần tử.

Ví dụ sai về nguyên tắc:

```java
// Nếu equals dùng Arrays.equals(bytes, other.bytes) thì:
return Objects.hash(name, bytes); // Sai ý nghĩa: bytes là mảng.
```

Với `byte[]`, đối số `bytes` được coi như **một đối tượng mảng** của `Objects.hash`. Mảng byte kế thừa `hashCode` dựa trên danh tính từ `Object`; hai mảng có nội dung bằng nhau không được đảm bảo cho hash bằng nhau.

Đúng hơn:

```java
int result = Objects.hashCode(name);
result = 31 * result + Arrays.hashCode(bytes);
return result;
```

Với mảng `Object[]` có phần tử là những mảng con cần so sánh sâu, dùng cặp tương ứng:

- `Arrays.deepEquals(a, b)` với `Arrays.deepHashCode(a)`.
- `Arrays.equals(a, b)` với `Arrays.hashCode(a)` nếu muốn so theo phần tử ở một cấp (các mảng lồng nhau trong `Object[]` vẫn được so bằng quan hệ của chính chúng nếu không dùng phiên bản `deep`).

**Một lưu ý về varargs:** Khi truyền trực tiếp `Object[]` vào `Objects.hash(Object...)`, chính các phần tử của nó có thể được coi là các đối số varargs. Do đó cách gọi `Objects.hash(array)` dễ gây nhầm trong ngữ cảnh mảng. Khi yêu cầu là hash theo nội dung mảng, hãy gọi rõ `Arrays.hashCode(array)` hoặc `Arrays.deepHashCode(array)` tùy ngữ nghĩa.

### 6.1. Ví dụ hoàn chỉnh với trường mảng

Tạo tệp **`ArrayFieldHashDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ArrayFieldHashDemo {
    static final class PacketKey {
        private final String protocol;
        private final byte[] payload;

        PacketKey(String protocol, byte[] payload) {
            this.protocol = Objects.requireNonNull(protocol);
            this.payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof PacketKey other)) {
                return false;
            }
            return protocol.equals(other.protocol)
                    && Arrays.equals(payload, other.payload);
        }

        @Override
        public int hashCode() {
            int result = Objects.hashCode(protocol);
            result = 31 * result + Arrays.hashCode(payload);
            return result;
        }

        int firstByte() {
            return payload[0];
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        PacketKey first = new PacketKey("tcp", source);
        PacketKey same = new PacketKey("tcp", new byte[] {1, 2, 3});
        PacketKey changed = new PacketKey("tcp", new byte[] {1, 2, 4});

        System.out.println("equal payloads: " + first.equals(same));
        System.out.println("equal hashes: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("different payloads: "
                + first.equals(changed));

        Set<PacketKey> packets = new HashSet<>();
        packets.add(first);
        System.out.println("set finds equal payload: "
                + packets.contains(same));

        source[0] = 99; // Đổi mảng bên ngoài.
        System.out.println("internal first byte: " + first.firstByte());
        System.out.println("set still finds original: "
                + packets.contains(same));
    }
}
```

Chạy:

```bash
javac ArrayFieldHashDemo.java
java ArrayFieldHashDemo
```

**Đầu ra:**

```text
equal payloads: true
equal hashes: true
different payloads: false
set finds equal payload: true
internal first byte: 1
set still finds original: true
```

Ở đây `PacketKey` tạo **bản sao phòng vệ** (`clone`) của mảng trong constructor. Vì mã bên ngoài chỉ giữ mảng `source`, thay đổi `source` không làm đổi trạng thái nội bộ của khóa. Điều này đặc biệt quan trọng khi khóa đã được đưa vào `HashSet` hoặc `HashMap`.

**Giới hạn ví dụ:** `firstByte()` giả định payload không rỗng, chỉ phục vụ quan sát nội dung trong ví dụ đã dùng mảng ba phần tử. Trong API thực tế, phương thức truy cập cần xử lý trường hợp rỗng và việc xuất mảng ra bên ngoài cũng phải được kiểm soát (ví dụ trả bản sao).

## 7. Trường đối tượng và cấu trúc lồng nhau

Đối với trường là một đối tượng thông thường, dùng `Objects.hashCode(field)` hoặc `field.hashCode()` (nếu biết chắc khác `null`). Để toàn bộ mã băm phù hợp với `equals`, chính kiểu của trường đó cũng cần tuân thủ hợp đồng `equals/hashCode`.

Ví dụ:

```java
final class Address {
    private final String city;
    private final String street;

    // Constructor, equals và hashCode đầy đủ sẽ cần được triển khai.
}
```

Nếu một `CustomerKey` so sánh `customerId` và `address` bằng `Objects.equals`, mã băm có thể là:

```java
return Objects.hash(customerId, address);
```

Hai đoạn trên **chỉ minh họa thiết kế**, chưa phải chương trình độc lập để biên dịch/chạy; cần khai báo phần còn lại của lớp và bảo đảm `Address` có `equals/hashCode` phù hợp với ý nghĩa giá trị.

Không nên gọi `address.toString().hashCode()` chỉ để “lấy hash” của đối tượng. `toString()` vốn phục vụ trình bày/chẩn đoán, thường không được thiết kế làm định nghĩa bằng nhau. Cũng không nên dùng `System.identityHashCode(address)` nếu `equals` của lớp coi hai địa chỉ khác instance nhưng có nội dung giống nhau là bằng nhau.

Đối với tập hợp tiêu chuẩn:

- `List.hashCode()` kết hợp hash của các phần tử **có xét thứ tự**, phù hợp với `List.equals`.
- `Set.hashCode()` dựa trên các phần tử và **không phụ thuộc thứ tự duyệt**, phù hợp với `Set.equals`.
- `Map.hashCode()` dựa trên các entry, phù hợp với `Map.equals`.
- Một đối tượng giữ collection mutable làm thành phần bình đẳng có nguy cơ bị đổi hash khi collection bị chỉnh sửa. Tránh để bên ngoài sửa collection nội bộ khi nó là thành phần của khóa.

## 8. Kiểu đặc biệt và giá trị `null`

### 8.1. Kiểu nguyên thủy

Hãy dùng hàm hash chuẩn cho kiểu tương ứng, nhất là `long`, `float`, `double`. Chẳng hạn:

```java
int result = 1;
result = 31 * result + Long.hashCode(orderId);
result = 31 * result + Double.hashCode(amount);
result = 31 * result + Boolean.hashCode(confirmed);
```

Đây là **đoạn minh họa** giả định các biến trường đã được khai báo trong lớp.

Tránh viết `(int) orderId` cho trường `long`: phép ép cắt bỏ các bit cao và dễ tạo va chạm không cần thiết. Tránh ép số thực về `int` nếu quan hệ bằng nhau phân biệt các giá trị thực.

Với `float`/`double`, `Float.hashCode` và `Double.hashCode` có ngữ nghĩa bit nhất quán với cách so sánh giá trị theo `Float.equals`/`Double.equals`. Nếu `equals` của lớp dùng trực tiếp toán tử `==` trên giá trị dấu phẩy động thì cần rất cẩn thận: chẳng hạn `+0.0 == -0.0` theo `==` là `true`, nhưng hai giá trị đó có hash khác nhau theo `Double.hashCode`. Một phương thức `hashCode` dùng `Double.hashCode` khi `equals` dùng `==` có thể vi phạm hợp đồng ở trường hợp này. Hãy thống nhất chính sách so sánh (ví dụ dùng `Double.compare` trong `equals` cùng `Double.hashCode` trong hash) thay vì ghép các cách tính không tương thích.

### 8.2. `null`

`Objects.hash(region, category)` tự xử lý các giá trị `null`. Với công thức thủ công:

```java
int result = 1;
result = 31 * result + Objects.hashCode(region);
result = 31 * result + Objects.hashCode(category);
return result;
```

`Objects.hashCode(null)` trả `0`; không có `NullPointerException`. Tránh `region.hashCode()` khi có khả năng `region == null`.

### 8.3. `record`

Java `record` tự cung cấp `equals` và `hashCode` từ **toàn bộ record component**, trừ khi bạn chủ động ghi đè:

```java
record ProductKey(String code, int revision, boolean active) {}
```

Đây là cách gọn để mô hình hóa value object đơn giản. Tuy nhiên:

- Nếu record có component dạng **mảng**, `equals`/`hashCode` mặc định của record dùng ngữ nghĩa của component mảng (so theo tham chiếu), **không tự so nội dung mảng**. Nếu muốn bình đẳng theo phần tử, phải tự thiết kế cặp `equals/hashCode` thích hợp hoặc dùng cấu trúc khác.
- `record` có các field thành phần `final`, nhưng **không tự làm bất biến sâu** một component tham chiếu tới collection/mảng mutable.
- Nếu nghiệp vụ cần một tập trường khác với toàn bộ component tham gia bình đẳng, nên thiết kế value object/cấu trúc rõ ràng và duy trì nhất quán giữa `equals` với `hashCode`.

## 9. Trường thay đổi sau khi đưa đối tượng vào `HashMap`/`HashSet`

Xét lớp mutable mà `equals` và `hashCode` đều dựa trên `id`:

```java
final class MutableKey {
    int id;

    MutableKey(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
```

Đoạn trên là **minh họa lớp**; có thể dùng trong một tệp Java thích hợp với khai báo lớp ngoài hoặc trong `main` của một chương trình.

Khi `id` thay đổi sau khi thêm khóa vào `HashMap`, việc tra cứu có thể không tìm ra khóa nữa vì mã băm lúc tra cứu khác mã băm khi khóa được phân vào cấu trúc dữ liệu. Kể cả `equals/hashCode` hiện vẫn nhất quán với nhau, thay đổi trạng thái tham gia hash vẫn khiến ứng dụng gặp vấn đề.

**Quy tắc thực hành:** Với khóa theo giá trị, ưu tiên thiết kế bất biến; các trường tham gia `equals/hashCode` nên được cố định trong suốt thời gian dùng làm khóa. Nếu buộc phải sửa, loại bỏ khóa bằng trạng thái cũ rồi tái thêm theo trạng thái mới ở thời điểm thích hợp, với cơ chế quản lý nhất quán.

## 10. Cách kiểm tra chất lượng triển khai

Ngoài việc chạy ví dụ, nên kiểm tra các nhóm tình huống sau:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hai instance có các trường theo `equals` giống nhau | `equals == true` và `hashCode` bằng nhau |
| Khác đúng một trường tham gia `equals` | `equals == false`; hash **có thể** bằng hoặc khác, không cần khẳng định |
| Trường tham chiếu có thể `null` | Không có `NullPointerException`; cùng trạng thái `null` cho hash nhất quán |
| Có mảng so theo nội dung | Cặp `Arrays.equals/hashCode` hoặc `deepEquals/deepHashCode` được dùng tương ứng |
| Có trường mutable | Không bị chỉnh sửa khi làm khóa hoặc có chiến lược quản lý rõ ràng |
| Dùng lớp thành phần | Thành phần đó cũng có `equals/hashCode` tương thích |
| Dùng `HashSet`/`HashMap` | Có thể tìm phần tử/khóa bằng một instance khác mà `equals` coi là bằng nhau |

Những lỗi thường thấy trong review:

1. `equals` kiểm tra `name` và `age`, nhưng `hashCode` lại băm `name` với `createdAt`. Hai đối tượng bằng nhau có thể có hash khác nhau nếu `createdAt` khác.
2. Dùng `Objects.hash(bytes)` trong khi `equals` dùng `Arrays.equals(bytes, ...)`, dẫn đến băm danh tính mảng thay vì nội dung mảng.
3. Gọi `field.hashCode()` cho một trường có thể `null`.
4. Tính hash một lần rồi cache nhưng các trường liên quan vẫn mutable và có thể thay đổi, khiến hash cache không còn phản ánh trạng thái so sánh.
5. Tin rằng hash khác nhau là điều kiện cần để các đối tượng khác nhau; thực tế collision là hợp lệ.
6. Đưa dữ liệu hash vào định danh lâu dài, chữ ký bảo mật hoặc phương thức kiểm tra duy nhất: `hashCode()` không được thiết kế cho các mục đích đó.

## 11. Bài tập tự kiểm tra

**Bài 1.** Lớp `BookKey` so sánh theo `isbn` và `edition`. Mã băm nào dễ đọc và phù hợp?

```java
@Override
public int hashCode() {
    return Objects.hash(isbn, edition);
}
```

**Đáp án:** Phù hợp nếu `equals` cũng xét đúng hai trường đó với quy tắc tương ứng, còn các giá trị ổn định khi đối tượng làm khóa.

**Bài 2.** `equals` chỉ so `username` và `tenantId`. Có được thêm `lastLoginTime` vào `hashCode` không?

**Đáp án:** Không nên. Hai đối tượng có cùng `username`/`tenantId` nhưng `lastLoginTime` khác có thể `equals == true` trong khi hash khác nhau, gây vi phạm hợp đồng.

**Bài 3.** Lớp chứa `int[] scores` và dùng `Arrays.equals(scores, other.scores)`. Mã băm của trường `scores` cần tính bằng gì?

**Đáp án:** `Arrays.hashCode(scores)`, sau đó kết hợp với hash các trường còn lại. `scores.hashCode()` băm theo danh tính mảng và không phù hợp nếu bằng nhau được xác định theo nội dung.

**Bài 4.** Hai đối tượng khác nhau có được trả cùng hash không?

**Đáp án:** Có. Collision không vi phạm hợp đồng; quan hệ bắt buộc chỉ đi theo chiều `equals == true ⇒ hash giống nhau`.

**Bài 5.** Tại sao `Objects.hash(...)` thuận tiện nhưng công thức `31 * result + ...` vẫn phổ biến?

**Đáp án:** `Objects.hash` ngắn gọn, xử lý `null` và boxing tự động, dễ giảm lỗi bỏ sót trường. Công thức thủ công cho phép kiểm soát chính xác kiểu dữ liệu và tránh một số chi phí varargs/boxing ở đường nóng, đổi lại cần cẩn thận chọn đúng trường, đúng thứ tự, đúng hàm hash thành phần.

## Ghi nhớ

**Bắt đầu từ `equals`, rồi chọn cùng những thuộc tính quyết định bằng nhau để kết hợp thành `hashCode`.** Với trường thông thường, `Objects.hash(field1, field2, ...)` là lựa chọn mặc định dễ dùng; với nhu cầu kiểm soát hiệu năng hoặc dữ liệu đặc biệt, kết hợp thủ công bằng `31` và các hàm hash theo kiểu. Với mảng, phải dùng `Arrays.hashCode`/`Arrays.deepHashCode` nếu định nghĩa bằng nhau dựa trên nội dung. Bảo đảm hash ổn định khi đối tượng làm khóa; chấp nhận collision như một phần bình thường của hashing.
