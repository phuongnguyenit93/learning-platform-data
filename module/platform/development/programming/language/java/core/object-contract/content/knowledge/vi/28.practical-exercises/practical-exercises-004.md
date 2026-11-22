# Thực nghiệm va chạm hash với các đối tượng không bằng nhau

**Va chạm hash (hash collision)** xảy ra khi hai đối tượng có cùng giá trị `hashCode()` nhưng **`equals()` trả về `false`**. Đây là tình huống hợp lệ theo hợp đồng của Java. Một cấu trúc như `HashMap` hoặc `HashSet` phải xử lý được va chạm để vẫn phân biệt các khóa khác nhau.

Bài thực hành này trả lời bằng mã chạy được ba câu hỏi: làm sao tạo và quan sát va chạm; vì sao hai khóa trùng hash vẫn cùng tồn tại trong collection; và đâu là ranh giới giữa tính **đúng** của `equals/hashCode` với **chất lượng phân phối** của hàm hash.

## 1. Hợp đồng cần nắm trước khi thử nghiệm

Với hai tham chiếu đối tượng không `null` là `a` và `b`:

- Nếu `a.equals(b) == true`, **bắt buộc** `a.hashCode() == b.hashCode()`.
- Nếu `a.hashCode() == b.hashCode()`, **không thể kết luận** `a.equals(b) == true`.
- Nếu `a.hashCode() != b.hashCode()` và các phương thức tuân thủ hợp đồng, có thể kết luận `a` và `b` không bằng nhau.
- Trong quá trình dữ liệu dùng để so sánh không thay đổi, `equals()` và `hashCode()` phải cho kết quả nhất quán. Tránh thay đổi trường tham gia hash khi đối tượng đang làm khóa của `HashMap` hoặc phần tử của `HashSet`.

Có thể hình dung:

```text
                a.hashCode() == b.hashCode() ?
                           |
              +------------+------------+
              |                         |
             Không                      Có
              |                         |
      Hai khóa không bằng nhau   Chưa biết bằng nhau
                                        |
                                  Kiểm tra equals()
                                    /        \
                                  true       false
                                   |           |
                              Cùng khóa    Va chạm hash
```

Mũi tên **`equals == true → hashCode bằng nhau`** là một chiều. Hàm băm biến không gian giá trị đối tượng rất lớn thành một số nguyên `int` 32 bit, vì thế nhiều giá trị khác nhau có thể chia sẻ một số hash. Thậm chí một hàm trả về cùng hằng số cho mọi đối tượng vẫn có thể *đúng hợp đồng* nhưng phân phối hash cực kém.

## 2. Va chạm tự nhiên có thể tái hiện với `String`

Trong Java, hai chuỗi khác nhau `"Aa"` và `"BB"` có hash code giống nhau:

```text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
```

Ở đây 65/97/66 là giá trị ký tự `A`, `a`, `B` trong UTF-16; công thức đơn giản cho chuỗi dài hai ký tự là `31 * c0 + c1`. Với chuỗi dài hơn, `String.hashCode()` tích lũy theo đa thức nhân 31 trong số nguyên 32 bit, cho phép tràn theo quy tắc số học `int`.

Nhưng `"Aa".equals("BB")` là `false` vì nội dung chuỗi khác nhau. Đây là **một va chạm thật của `String.hashCode()`**, không cần sửa JDK, can thiệp bộ nhớ hoặc dùng thư viện bên ngoài.

## 3. Chương trình Java 17+ có thể chạy độc lập

Chương trình chứa hai thí nghiệm:

1. **Va chạm tự nhiên:** dùng trực tiếp `String` `"Aa"` và `"BB"` làm khóa.
2. **Va chạm có chủ đích:** định nghĩa `ProductKey` có `equals()` so sánh `sku` nhưng `hashCode()` luôn trả về `7` để buộc các khóa khác nhau đụng hash.

Lưu nội dung sau thành tệp **`HashCollisionDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashCollisionDemo {
    public static void main(String[] args) {
        // Thí nghiệm 1: va chạm thật với String.
        String a = "Aa";
        String b = "BB";

        System.out.println("String hash: "
                + a.hashCode() + " / " + b.hashCode());
        System.out.println("String equals: " + a.equals(b));
        System.out.println("Sai neu chi so hash: "
                + (a.hashCode() == b.hashCode()));

        Set<String> stringSet = new HashSet<>();
        stringSet.add(a);
        stringSet.add(b);
        System.out.println("String set size: " + stringSet.size());

        Map<String, Integer> stringMap = new HashMap<>();
        stringMap.put(a, 10);
        stringMap.put(b, 20);
        System.out.println("String map values: "
                + stringMap.get(a) + " / " + stringMap.get(b));

        // Thí nghiệm 2: cố ý làm mọi ProductKey trùng hash.
        ProductKey first = new ProductKey("SKU-A");
        ProductKey second = new ProductKey("SKU-B");
        ProductKey sameAsFirst = new ProductKey("SKU-A");

        System.out.println("Custom hash: "
                + first.hashCode() + " / " + second.hashCode());
        System.out.println("Distinct keys equal: "
                + first.equals(second));
        System.out.println("Equivalent keys equal: "
                + first.equals(sameAsFirst));

        Set<ProductKey> productSet = new HashSet<>();
        productSet.add(first);
        productSet.add(second);
        productSet.add(sameAsFirst);
        System.out.println("Custom set size: " + productSet.size());

        Map<ProductKey, String> productMap = new HashMap<>();
        productMap.put(first, "gia tri A");
        productMap.put(second, "gia tri B");
        System.out.println("Custom map size: " + productMap.size());
        System.out.println("Lookup equivalent: "
                + productMap.get(sameAsFirst));
        System.out.println("Lookup second: "
                + productMap.get(second));
    }

    // Ví dụ cố ý có hashCode kém để quan sát va chạm.
    // Không sao chép chiến lược hash hằng số vào mã production.
    static final class ProductKey {
        private final String sku;

        ProductKey(String sku) {
            this.sku = Objects.requireNonNull(sku);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ProductKey other)) {
                return false;
            }
            return sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return 7; // Cố ý gây va chạm để thực nghiệm.
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac HashCollisionDemo.java
java HashCollisionDemo
```

**Stdout chính xác:**

```text
String hash: 2112 / 2112
String equals: false
Sai neu chi so hash: true
String set size: 2
String map values: 10 / 20
Custom hash: 7 / 7
Distinct keys equal: false
Equivalent keys equal: true
Custom set size: 2
Custom map size: 2
Lookup equivalent: gia tri A
Lookup second: gia tri B
```

Kết quả không phụ thuộc thứ tự duyệt của `HashMap` hay `HashSet`: chương trình chỉ in các giá trị tra cứu trực tiếp và `size()`. Nếu thay bằng vòng `for` để in toàn bộ collection, **không được giả định thứ tự phần tử ổn định**.

## 4. Đọc kết quả thí nghiệm

### Thí nghiệm 1: cùng hash nhưng cả hai chuỗi vẫn tồn tại

`"Aa"` và `"BB"` có cùng hash `2112`, song `String.equals()` xác nhận chúng khác nhau. `HashSet.add(a)` và `HashSet.add(b)` đều thêm được khóa riêng, vì vậy `stringSet.size() == 2`.

Với `HashMap`, hai thao tác `put("Aa", 10)` và `put("BB", 20)` giữ **hai ánh xạ riêng**. `get("Aa")` trả về `10`; `get("BB")` trả về `20`. Va chạm **không tự động ghi đè** giá trị của khóa khác.

Ngược lại, câu lệnh sai sau coi hai chuỗi là bằng nhau chỉ vì hash trùng:

```java
boolean incorrect = "Aa".hashCode() == "BB".hashCode();
// incorrect == true, dù "Aa".equals("BB") == false.
```

**Không dùng hash code như ID duy nhất hoặc thay thế cho `equals()`.** Hash hữu ích để thu hẹp ứng viên cần so sánh, không chứng minh hai đối tượng có nội dung bằng nhau.

### Thí nghiệm 2: phân biệt “hash trùng” và “khóa tương đương”

Cả `first`, `second` và `sameAsFirst` đều trả về hash `7`. Tuy nhiên:

| Cặp đối tượng | Kết quả `equals` | Ý nghĩa |
| --- | --- | --- |
| `first` / `second` | `false` | SKU khác nhau; đây là một va chạm. |
| `first` / `sameAsFirst` | `true` | SKU giống nhau; hai thể hiện của cùng một khóa logic. |
| `second` / `sameAsFirst` | `false` | SKU khác nhau; tiếp tục là một va chạm. |

`productSet.size() == 2` vì hai giá trị SKU là khác nhau, còn đối tượng thứ ba tương đương đối tượng thứ nhất và không tạo phần tử logic mới. Tương tự, `productMap.size() == 2`; truy vấn bằng một đối tượng mới có SKU `"SKU-A"` vẫn tìm ra giá trị gắn với `first`.

Điều này chứng minh **hash bằng nhau không đủ để xem là phần tử trùng lặp**. Collection dựa trên hash còn phải xét tính tương đương theo `equals()` (hoặc quan hệ so sánh khóa tương đương theo hợp đồng tương ứng).

## 5. Collection giải quyết va chạm như thế nào?

Nhìn ở mức khái niệm, tra cứu trong `HashMap` gồm các bước:

1. Tính hash từ khóa được cung cấp; `HashMap` có thể biến đổi hash này thêm để chọn vị trí lưu trong bảng nội bộ.
2. Xác định vị trí/nhóm ứng viên từ hash.
3. Trong nhóm ứng viên, đối chiếu hash và tính bằng nhau của khóa. Khóa có cùng hash nhưng `equals() == false` vẫn là khóa khác.
4. Nếu có khóa tương đương, `get` trả về giá trị tương ứng; nếu `put` với khóa tương đương, giá trị của ánh xạ hiện hữu được thay thế. Nếu không có, `put` tạo ánh xạ mới.

`HashSet` sử dụng cấu trúc dựa trên hash nên cũng cần phân biệt các phần tử cùng hash bằng quan hệ bằng nhau.

Sơ đồ minh họa (không mô tả layout bộ nhớ chính xác của từng bản JDK):

```text
hashCode("Aa") = 2112 ─┐
                       ├── Nhóm ứng viên có hash trùng
hashCode("BB") = 2112 ─┘          |
                                  +-- equals("Aa", "BB") -> false
                                  +-- Có thể lưu/tra cứu hai khóa riêng

hashCode(ProductKey("SKU-A")) = 7 ─┐
                                   ├── Nhóm ứng viên cùng hash
hashCode(ProductKey("SKU-A")) = 7 ─┘          |
                                              +-- equals -> true
                                              +-- Một khóa logic
```

Một số bản hiện thực `HashMap` có thể chuyển nhóm chứa nhiều phần tử va chạm sang cấu trúc cây dưới điều kiện nhất định. Đây là **chi tiết tối ưu của hiện thực**, không phải lý do để dựa vào bucket cụ thể, thứ tự duyệt, số lần gọi `equals` hoặc thời gian thực thi cố định trong mã ứng dụng.

## 6. Hàm hash tốt khác với hàm hash đúng hợp đồng

Hàm `ProductKey.hashCode()` trả về `7` cho mọi trường hợp nên **không vi phạm** quy tắc “đã bằng nhau thì hash phải bằng nhau”. Nhưng nó không phân tán được các giá trị SKU khác nhau, khiến nhiều thao tác phải xử lý chung một nhóm ứng viên.

Trong mã nghiệp vụ, phiên bản hợp lý hơn là dựa trên chính trường tham gia `equals`:

```java
@Override
public int hashCode() {
    return sku.hashCode();
}
```

Đoạn trên là **phương thức thay thế trong lớp `ProductKey` ở ví dụ**, không phải một chương trình `main` độc lập. Vì `sku` là `String` không `null` và bất biến, cách này tuân thủ hợp đồng và thông thường phân phối khóa tốt hơn hằng số `7`. Nó vẫn có thể va chạm, như `"Aa"` và `"BB"` đã chứng minh.

Các tiêu chí cần tách bạch:

| Tiêu chí | Yêu cầu |
| --- | --- |
| **Đúng hợp đồng** | Bất kỳ hai đối tượng `equals == true` đều có hash bằng nhau. |
| **Nhất quán** | Khi dữ liệu tham gia so sánh không đổi, hash không thay đổi giữa các lần gọi theo hợp đồng. |
| **Phân phối hợp lý** | Với dữ liệu thực tế, hạn chế việc quá nhiều khóa không bằng nhau trùng hash để cải thiện hiệu năng trung bình. |
| **Không đòi hỏi duy nhất** | Không thể bảo đảm mỗi giá trị đối tượng có hash riêng với `int` 32 bit. |

Chất lượng phân phối hash phụ thuộc dữ liệu sử dụng. Trong một ứng dụng có dữ liệu đối kháng, nhiều khóa có thể được chọn để gây va chạm hàng loạt; đây là vấn đề hiệu năng cần theo dõi, dù kết quả tra cứu vẫn đúng nếu hợp đồng được giữ.

## 7. Những lỗi dễ mắc khi thực nghiệm

### Lỗi 1: khẳng định hai đối tượng bằng nhau chỉ vì hash trùng

Sai:

```java
boolean same = a.hashCode() == b.hashCode();
```

Đúng khi cần kiểm tra bình đẳng đối tượng theo hợp đồng:

```java
boolean same = Objects.equals(a, b);
```

Với các tham chiếu có thể `null`, `Objects.equals` xử lý trường hợp `null` và gọi `equals` khi cần. Nó không biến một hiện thực `equals` sai thành đúng.

### Lỗi 2: cố sửa `equals()` để “tránh va chạm”

Va chạm không đồng nghĩa `equals()` có lỗi. `equals()` phải biểu đạt **quan hệ bình đẳng có ý nghĩa của lớp**; `hashCode()` phải nhất quán với quan hệ đó. Việc ghép hash vào điều kiện `equals()` có thể làm kết quả phụ thuộc vào một mã băm vốn không duy nhất.

### Lỗi 3: override một phương thức nhưng quên phương thức còn lại

Nếu override `equals()` để hai đối tượng khác địa chỉ bộ nhớ được xem là bằng nhau, cũng phải override `hashCode()` tương thích. Nếu không, `HashMap` hoặc `HashSet` có thể không tìm ra khóa tương đương, hoặc chứa hai phần tử mà `equals()` tuyên bố là bằng nhau.

### Lỗi 4: thay đổi khóa sau khi thêm vào hash collection

Nếu dùng một trường có thể đổi trong `equals/hashCode`, việc cập nhật trường đó có thể đổi hash và khiến tra cứu thất bại. `HashMap` không tự chuyển mục đã lưu sang vị trí mới chỉ vì đối tượng khóa bị sửa. Trong ví dụ, `sku` là `final` để tránh sai lầm này.

### Lỗi 5: dùng thời gian một lần chạy làm kết luận hiệu năng

Bài này chứng minh **tính đúng khi va chạm**, không phải benchmark. Kết quả thời gian của một lần chạy ngắn còn chịu ảnh hưởng JIT, khởi động JVM, GC, kích thước bảng và dữ liệu đầu vào. Nếu cần đánh giá tốc độ giữa hàm hash hằng số và hàm hash tốt, hãy dùng tập khóa đủ lớn, phân phối đầu vào xác định và công cụ benchmark phù hợp (ví dụ JMH) sau khi xác minh tính đúng.

## 8. Bài kiểm tra mở rộng

Có thể chỉnh chương trình để kiểm tra thêm các tình huống sau:

1. **Thêm lại một khóa tương đương:** gọi `productMap.put(sameAsFirst, "gia tri A moi")`. Kích thước map vẫn là `2`; tra cứu bằng `first` trả về giá trị mới vì `first.equals(sameAsFirst) == true`.
2. **Thêm khóa thứ ba không bằng hai khóa còn lại nhưng cũng có hash `7`:** dùng `new ProductKey("SKU-C")`. Kích thước map tăng lên `3` nếu `put` khóa đó; ba khóa vẫn tra cứu độc lập.
3. **Đổi `hashCode()` sang `sku.hashCode()`:** chạy lại cùng ví dụ. Tính bằng nhau, kích thước collection và kết quả tra cứu giữ nguyên. Cặp `"SKU-A"`/`"SKU-B"` không cần cùng hash nữa.
4. **Thử hai khóa chuỗi va chạm khác:** thay các SKU bằng `"Aa"` và `"BB"` trong phiên bản `sku.hashCode()`; cùng hash `2112` nhưng `equals()` vẫn phân biệt được hai đối tượng.

Không cần kiểm tra kích thước bucket hay truy cập cấu trúc nội bộ `HashMap` để xác nhận các kết luận trên. Các kiểm tra có giá trị nhất là **`equals`, `hashCode`, `size`, `get` và giá trị khi cập nhật một khóa tương đương**.

**Kết luận kỹ thuật:** `hashCode()` giúp tổ chức và thu hẹp nhóm ứng viên; **`equals()` quyết định bình đẳng logic**. Va chạm giữa các đối tượng không bằng nhau là bình thường; cấu trúc hash đúng phải giữ được từng khóa riêng biệt, còn thiết kế hash tốt nhằm giảm chi phí xử lý va chạm.
