# Loại phần tử trùng bằng distinct với equals và hashCode

Trong nhiều ứng dụng, dữ liệu nhận từ API, tệp nhập liệu hoặc cơ sở dữ liệu có thể lặp lại: cùng một mã sản phẩm xuất hiện nhiều lần, cùng một người dùng được ghi ở nhiều dòng, hoặc một danh sách từ khóa chứa các giá trị trùng nhau. Với **Java Stream API**, ta có thể dùng `distinct()` để giữ lại những phần tử **khác nhau theo quy tắc bình đẳng của Java**.

Điểm cần hiểu ngay từ đầu: `distinct()` **không tự biết** hai sản phẩm có cùng mã hay không. Với Stream đối tượng, nó dựa trên `equals()` để xác định bằng nhau và `hashCode()` để hỗ trợ tìm phần tử trùng. Vì vậy, kết quả của `distinct()` phụ thuộc vào **cách lớp dữ liệu định nghĩa sự bằng nhau**.

Bài thuộc chương **Thứ tự, loại trùng và cắt lát** của module **JAVA_STREAM_API**. Sau bài này, bạn sẽ sử dụng được `distinct()` trong pipeline lazy, giải thích mối quan hệ giữa `equals` và `hashCode`, hiểu phần tử nào được giữ khi nguồn có thứ tự, nhận biết chi phí bộ nhớ và tránh lỗi với đối tượng mutable, Stream song song và dữ liệu vô hạn.

## 1. Bài toán đầu tiên: loại mã trùng

Giả sử hệ thống nhận danh sách các mã sản phẩm:

~~~java
List<String> codes = List.of(
    "SP01", "SP02", "SP01", "SP03", "SP02"
);
~~~

Yêu cầu là thu được `SP01`, `SP02` và `SP03`, mỗi mã một lần.

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class DistinctStringDemo {
    public static void main(String[] args) {
        List<String> codes = List.of(
            "SP01", "SP02", "SP01", "SP03", "SP02"
        );

        List<String> uniqueCodes = codes.stream()
            .distinct()
            .collect(Collectors.toList());

        System.out.println(uniqueCodes); // [SP01, SP02, SP03]
        System.out.println(codes.size());  // 5, nguồn vẫn giữ nguyên
    }
}
~~~

Ví dụ dùng `List.of` (Java 9+); `distinct()` có từ Java 8. Với Java 16+, có thể dùng `stream().distinct().toList()` để nhận danh sách không cho phép sửa.

Ta đọc pipeline như sau:

1. `codes.stream()` tạo Stream từ danh sách, giữ **encounter order** của `List`.
2. `distinct()` tạo một Stream trung gian chỉ phát ra các giá trị khác nhau.
3. `collect(Collectors.toList())` là phép toán kết thúc, tạo danh sách kết quả.

Trong nguồn có thứ tự, `distinct()` là **stable**: nếu nhiều phần tử bằng nhau, phần tử **xuất hiện đầu tiên** theo encounter order được giữ. Do đó, `SP01` ở vị trí đầu được giữ, bản sao `SP01` ở vị trí thứ ba bị loại.

`distinct()` không sửa danh sách `codes` và không trả về `Set`; kết quả vẫn là một **Stream** để tiếp tục `filter`, `map`, `sorted` hoặc các phép toán khác.

## 2. Hợp đồng của distinct trong Stream API

Chữ ký thường dùng là:

~~~java
Stream<T> distinct()
~~~

`distinct()` là **intermediate operation** có trạng thái (*stateful*): muốn biết giá trị mới có trùng hay không, quá trình xử lý phải theo dõi những giá trị tương đương đã gặp.

~~~mermaid
flowchart LR
    A["Nguồn: A, B, A, C, B"] --> B["distinct()"]
    B --> C["Stream: A, B, C"]
    C --> D["collect(toList())"]
    D --> E["List: A, B, C"]
~~~

Đặc tính quan trọng:

| Câu hỏi | Câu trả lời |
|---|---|
| `distinct()` có làm thay đổi kiểu phần tử không? | **Không**. `Stream<T>` vẫn là `Stream<T>`. |
| Nó có cần phép toán kết thúc không? | **Có** để thực hiện việc xử lý khi cần; nó là thao tác trung gian lazy. |
| Nó có sửa collection gốc không? | **Không**, bản thân thao tác loại trùng không sửa nguồn. |
| Nó giữ đại diện nào khi nguồn có thứ tự? | Phần tử **đầu tiên** trong nhóm các phần tử bằng nhau. |
| Nó có luôn đảm bảo thứ tự của kết quả không? | **Không** nếu Stream không có encounter order hoặc đã được đánh dấu `unordered()`. |
| Có phải mọi phần tử đều luôn được duyệt không? | **Không nhất thiết**; phép toán kết thúc dừng sớm có thể chỉ cần một phần nguồn. |
| Có cần nhớ giá trị đã gặp không? | Thường **có**, nên có thể tốn bộ nhớ khi số giá trị duy nhất lớn. |

Lưu ý sự khác nhau giữa **thứ tự** và **bình đẳng**: `distinct()` quyết định phần tử nào trùng theo `equals()`, không theo comparator của `sorted()`, không theo `toString()`, và không theo một trường dữ liệu bất kỳ trừ khi lớp định nghĩa equality dựa trên trường đó.

## 3. equals và hashCode quyết định thế nào là “trùng”?

Trong Java, mọi lớp kế thừa `equals(Object)` và `hashCode()` từ `Object`. Hai phương thức có vai trò riêng:

- `equals(Object)` trả lời câu hỏi: **hai đối tượng có được xem là bằng nhau không?**
- `hashCode()` trả về một số nguyên dùng trong các cấu trúc dựa trên băm (*hash-based*), nhằm hỗ trợ tìm các đối tượng có khả năng bằng nhau.

Một cách hình dung:

~~~text
Phần tử mới
    |
    v
Tính hashCode()  ---> tìm nhóm ứng viên tương ứng
    |
    v
So sánh equals() với ứng viên
    |
    +-- Đã có phần tử bằng nhau: bỏ phần tử mới
    |
    +-- Chưa có phần tử bằng nhau: giữ phần tử mới
~~~

Sơ đồ trên mô tả **nguyên lý thường gặp của cấu trúc băm**, không cam kết thuật toán nội bộ của mọi phiên bản JDK. Hợp đồng của `Stream.distinct` là sự khác nhau theo `Object.equals`; một triển khai tối ưu hóa có thể lựa chọn cách thực hiện khác nhau.

### 3.1. String đã có equality theo nội dung

Hai đối tượng `String` khác tham chiếu nhưng cùng ký tự vẫn bằng nhau:

~~~java
String first = new String("JAVA");
String second = new String("JAVA");

System.out.println(first == second);      // false: khác tham chiếu
System.out.println(first.equals(second)); // true: cùng nội dung
System.out.println(first.hashCode() == second.hashCode()); // true

long uniqueCount = java.util.stream.Stream.of(first, second)
    .distinct()
    .count();

System.out.println(uniqueCount); // 1
~~~

Vì `String` định nghĩa `equals` và `hashCode` theo nội dung, `distinct()` hoạt động như mong đợi khi loại chuỗi trùng chính xác.

Nhưng `String.equals` **phân biệt chữ hoa/chữ thường** và phân biệt khoảng trắng:

~~~java
List<String> raw = List.of("Java", "java", " Java ", "JAVA");

System.out.println(raw.stream().distinct().count()); // 4
~~~

Nếu nghiệp vụ xem những chuỗi trên là cùng một mã, cần **chuẩn hóa trước khi loại trùng**:

~~~java
import java.util.Locale;

List<String> normalized = raw.stream()
    .map(String::trim)
    .map(text -> text.toUpperCase(Locale.ROOT))
    .distinct()
    .collect(java.util.stream.Collectors.toList());

System.out.println(normalized); // [JAVA]
~~~

`Locale.ROOT` phù hợp với quy tắc chuẩn hóa mã kỹ thuật không phụ thuộc locale người dùng; với tên người hoặc ngôn ngữ tự nhiên, chính sách so sánh và Unicode có thể phức tạp hơn.

### 3.2. Hai đối tượng có cùng dữ liệu vẫn có thể được xem là khác nhau

Nếu lớp không ghi đè `equals`, hành vi mặc định từ `Object` thường dựa trên **định danh đối tượng**. Hai thực thể được tạo bởi `new` khác nhau dù trường giống nhau:

~~~java
class Product {
    String code;

    Product(String code) {
        this.code = code;
    }
}

Product a = new Product("SP01");
Product b = new Product("SP01");

System.out.println(a.equals(b)); // false: chưa ghi đè equals
System.out.println(java.util.stream.Stream.of(a, b).distinct().count()); // 2
~~~

Ví dụ này hợp lệ về mặt ngôn ngữ nhưng **không đáp ứng yêu cầu loại sản phẩm trùng theo mã**. Để làm việc đó, cần xác định quy tắc equality cho lớp, hoặc ánh xạ sang mã trước khi gọi `distinct()`.

## 4. Viết equals và hashCode nhất quán cho đối tượng nghiệp vụ

Giả sử với ứng dụng hiện tại, **mã sản phẩm `sku`** là định danh duy nhất. Hai bản ghi cùng `sku` được coi là cùng sản phẩm, ngay cả khi mô tả tên khác nhau do dữ liệu cập nhật.

Ví dụ đầy đủ chạy trên Java 8+:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class ProductDistinctDemo {
    static final class Product {
        private final String sku;
        private final String name;

        Product(String sku, String name) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.name = Objects.requireNonNull(name, "name");
        }

        String getSku() {
            return sku;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Product)) {
                return false;
            }
            Product that = (Product) other;
            return sku.equals(that.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }

        @Override
        public String toString() {
            return sku + " - " + name;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
            new Product("SP01", "Bút xanh"),
            new Product("SP02", "Sổ tay"),
            new Product("SP01", "Bút xanh (dữ liệu nhập lại)"),
            new Product("SP03", "Thước")
        );

        List<Product> uniqueProducts = products.stream()
            .distinct()
            .collect(Collectors.toList());

        uniqueProducts.forEach(System.out::println);
    }
}
~~~

Kết quả:

~~~text
SP01 - Bút xanh
SP02 - Sổ tay
SP03 - Thước
~~~

Ở đây:

1. `equals` so sánh **`sku`**, là quy tắc nghiệp vụ đã chọn.
2. `hashCode` cũng tính từ **`sku`**, nên hai sản phẩm được xem là bằng nhau có cùng mã băm.
3. Vì nguồn là `List` có thứ tự, `distinct()` giữ sản phẩm `SP01` xuất hiện đầu, tức tên `Bút xanh`. Bản ghi `SP01` thứ hai không còn trong kết quả.

**Không có một quy tắc equals đúng cho mọi bài toán.** Nếu với hệ thống của bạn, hai sản phẩm cùng SKU nhưng khác phiên bản phải được xem là khác nhau, thì `sku` đơn lẻ chưa đủ. Cần xác định đầy đủ bộ khóa nghiệp vụ (ví dụ `sku` + `version`) rồi dùng chính bộ khóa đó trong **cả `equals` và `hashCode`**.

### 4.1. Hợp đồng bắt buộc của equals và hashCode

Theo hợp đồng của Java, `equals` phải tuân theo:

- **Reflexive:** với đối tượng không null, `x.equals(x)` là `true`.
- **Symmetric:** nếu `x.equals(y)` là `true` thì `y.equals(x)` cũng là `true`.
- **Transitive:** nếu `x.equals(y)` và `y.equals(z)` đều `true` thì `x.equals(z)` phải `true`.
- **Consistent:** khi thông tin dùng để so sánh không đổi, việc gọi nhiều lần phải cho kết quả nhất quán.
- **Không bằng null:** `x.equals(null)` là `false` với `x` không null.

Với `hashCode`:

- Nếu `x.equals(y)` là `true`, **bắt buộc** `x.hashCode() == y.hashCode()`.
- Nếu hai đối tượng có cùng mã băm, **không bắt buộc** chúng phải bằng nhau. Đây là **hash collision**, không tự nó là lỗi.
- Mã băm phải nhất quán trong lúc các thông tin ảnh hưởng đến equality chưa đổi.

Sai lầm phổ biến là **chỉ ghi đè `equals` nhưng quên `hashCode`**. Khi đó hai đối tượng được xem là bằng nhau có thể nhận mã băm khác nhau, dẫn đến hành vi sai trong `HashSet`, `HashMap` và các thao tác loại trùng dựa trên cấu trúc băm.

Cách viết điển hình:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Product)) return false;
    Product that = (Product) other;
    return Objects.equals(sku, that.sku);
}

@Override
public int hashCode() {
    return Objects.hash(sku);
}
~~~

Đây là một **phương án thay thế** cho cách viết trong ví dụ hoàn chỉnh phía trên, khi muốn sử dụng các tiện ích `Objects`. Không được chèn thêm hai phương thức này bên cạnh phương thức đã có trong cùng lớp. Với một khóa `String` không null, `sku.hashCode()` trực tiếp là đủ.

### 4.2. Vì sao trường tham gia equality nên bất biến?

Nếu sửa `sku` trong lúc Stream đang loại trùng, giá trị `hashCode` và quan hệ `equals` có thể thay đổi giữa quá trình đánh giá. Dữ liệu đang được ghi nhận theo mã băm cũ có thể không còn tìm được đúng như dự định.

Vì vậy, ví dụ dùng `private final String sku` và `Product` là lớp `final`. Với các trường khóa quan trọng hơn, có thể dùng object bất biến hoặc record, và **không thay đổi dữ liệu nguồn khi pipeline đang duyệt**.

Nếu bắt buộc cập nhật khóa nghiệp vụ, thường nên thực hiện cập nhật dữ liệu **trước** khi bắt đầu pipeline, hoặc xây dựng các đối tượng kết quả mới rồi loại trùng theo khóa mới.

## 5. Record, Lombok và các lớp sinh equals tự động

Từ **Java 16**, `record` là một cách ngắn gọn để biểu diễn dữ liệu:

~~~java
record Product(String sku, String name) {}

List<Product> products = List.of(
    new Product("SP01", "Bút xanh"),
    new Product("SP01", "Bút xanh (mới)")
);

System.out.println(products.stream().distinct().count()); // 2
~~~

Record mặc định tạo `equals` và `hashCode` từ **tất cả các thành phần**: `sku` **và** `name`. Vì tên khác nhau nên hai record trên **không bằng nhau**, dù mã giống nhau.

Đây là chỗ cần phân biệt:

| Thiết kế | Quy tắc equality mặc định/đã định nghĩa | Kết quả với cùng SKU, khác tên |
|---|---|---|
| Lớp thông thường, không ghi đè `equals` | Định danh đối tượng | Hai đối tượng riêng biệt |
| Lớp `Product` ở mục 4 | Chỉ theo `sku` | Một phần tử khi `distinct` |
| `record Product(String sku, String name)` | Theo cả `sku` và `name` | Hai phần tử |

Các công cụ như Lombok có thể sinh `equals` và `hashCode` dựa trên tập trường được cấu hình. **Đọc quy tắc equality thực tế** trước khi giả định `distinct` sẽ loại trùng theo ID.

Nếu chỉ cần loại trùng **mã sản phẩm**, không nhất thiết phải thay đổi equality của cả lớp. `products.stream().map(Product::sku).distinct()` sẽ cho các **mã duy nhất**, nhưng kết quả khi đó là `Stream<String>`, không còn là `Stream<Product>`.

## 6. Thứ tự nào được giữ sau distinct?

Một Stream có thể có *encounter order*: thứ tự phần tử do nguồn và các thao tác trước đó xác định. `List.stream()` thường có encounter order của List.

~~~java
List<String> names = List.of("An", "Bình", "An", "Chi", "Bình");

List<String> result = names.stream()
    .distinct()
    .collect(java.util.stream.Collectors.toList());

System.out.println(result); // [An, Bình, Chi]
~~~

Với Stream có encounter order, `distinct` **giữ phần tử đầu tiên trong mỗi nhóm tương đương**. Điều này quan trọng nếu hai đối tượng bằng nhau theo ID nhưng các thuộc tính hiển thị không giống nhau: bản ghi đầu tiên có thể là bản cũ.

Với nguồn **không có encounter order**, chẳng hạn một số nguồn `Set`, hoặc sau khi gọi `unordered()`, không nên kỳ vọng phần tử đại diện hay thứ tự kết quả xác định.

~~~java
List<String> unorderedResult = names.stream()
    .unordered()
    .distinct()
    .collect(java.util.stream.Collectors.toList());

// Có cùng tập giá trị {An, Bình, Chi}, nhưng không dựa vào thứ tự này.
~~~

`unordered()` không phải phép toán xáo trộn, và kết quả đôi khi **trông vẫn cùng thứ tự**. Ý nghĩa của nó là bỏ ràng buộc về encounter order, cho phép triển khai có nhiều tự do hơn. Không viết kiểm thử phụ thuộc thứ tự trong trường hợp đó.

### 6.1. distinct và sorted giải quyết hai vấn đề khác nhau

~~~java
List<String> input = List.of("C", "A", "C", "B");

List<String> uniqueSorted = input.stream()
    .distinct()
    .sorted()
    .collect(java.util.stream.Collectors.toList());

System.out.println(uniqueSorted); // [A, B, C]
~~~

`distinct` xác định phần tử **có trùng không**, còn `sorted` xác định **thứ tự**. `sorted(Comparator)` không mặc nhiên gộp hai phần tử có `comparator.compare(a, b) == 0` nếu `a.equals(b)` là `false`.

Một ví dụ dễ nhầm là `BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> values = List.of(
    new BigDecimal("1.0"),
    new BigDecimal("1.00")
);

System.out.println(values.get(0).compareTo(values.get(1))); // 0
System.out.println(values.get(0).equals(values.get(1)));    // false
System.out.println(values.stream().distinct().count());     // 2
~~~

`BigDecimal.compareTo` so sánh giá trị số, trong khi `BigDecimal.equals` còn phân biệt **scale**. Muốn coi `1.0` và `1.00` là một giá trị, hãy quyết định quy tắc chuẩn hóa hoặc dùng khóa tương đương phù hợp trước khi loại trùng; ví dụ `map(BigDecimal::stripTrailingZeros).distinct()` trong bài toán chấp nhận phép chuẩn hóa đó.

## 7. Thứ tự của các bước trong pipeline thay đổi kết quả

Cùng một nhóm phép toán, việc đặt `distinct` ở vị trí nào có thể làm kết quả khác nhau.

### 7.1. Chuẩn hóa trước hay sau distinct?

~~~java
List<String> source = List.of(" Java ", "JAVA", "Go");

List<String> correct = source.stream()
    .map(String::trim)
    .map(value -> value.toUpperCase(java.util.Locale.ROOT))
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [JAVA, GO]
~~~

Nếu dùng `distinct()` trước khi chuẩn hóa, ba chuỗi nguồn ban đầu vẫn khác nhau theo `String.equals` nên chúng đi qua bước loại trùng. Sau đó chúng có thể được biến đổi thành các chuỗi giống nhau mà **không được loại lần nữa**:

~~~java
List<String> stillDuplicated = source.stream()
    .distinct()
    .map(String::trim)
    .map(value -> value.toUpperCase(java.util.Locale.ROOT))
    .collect(java.util.stream.Collectors.toList());
// [JAVA, JAVA, GO]
~~~

Mẫu thường gặp khi cần khử trùng theo **giá trị sau biến đổi** là:

`nguồn → chuẩn hóa/map → filter nếu cần → distinct → thu kết quả`.

### 7.2. distinct trước hay sau limit?

~~~java
List<Integer> source = List.of(1, 1, 2, 3, 4);

List<Integer> distinctThenLimit = source.stream()
    .distinct()
    .limit(3)
    .collect(java.util.stream.Collectors.toList());
// [1, 2, 3]

List<Integer> limitThenDistinct = source.stream()
    .limit(3)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [1, 2]
~~~

- `distinct().limit(3)`: tìm tối đa **ba giá trị khác nhau** trong thứ tự nguồn.
- `limit(3).distinct()`: lấy **ba phần tử đầu vào**, rồi loại phần tử trùng trong lát cắt đó.

Với dữ liệu rất lớn, `limit` trước `distinct` có thể tiết kiệm công việc nhưng làm thay đổi nghĩa nghiệp vụ. Hãy ưu tiên đúng yêu cầu đầu ra.

### 7.3. filter trước distinct?

Nếu có thể lọc bớt phần tử mà không làm thay đổi định nghĩa nhóm trùng, `filter` trước `distinct` thường giảm số phần tử phải xét:

~~~java
List<Integer> result = List.of(-1, 2, 2, 3, -1, 4).stream()
    .filter(n -> n > 0)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
// [2, 3, 4]
~~~

Tuy nhiên, với đối tượng cùng khóa nhưng khác thuộc tính, **lọc trước hay sau khi chọn đại diện đầu tiên** có thể cho kết quả khác. Ví dụ nếu hai bản ghi cùng ID mà một bản không hợp lệ, hãy xác định nghiệp vụ muốn “giữ bản hợp lệ đầu tiên” hay “loại ID trùng theo bản ghi đầu tiên” trước khi sắp xếp các bước.

## 8. Loại trùng theo một khóa mà vẫn giữ cả đối tượng

Một yêu cầu phổ biến: “Giữ **toàn bộ sản phẩm**, nhưng chỉ một sản phẩm cho mỗi `sku`”. Nếu lớp hiện tại định nghĩa `equals` theo nhiều trường và không thể thay đổi, gọi `distinct()` trực tiếp sẽ **không đủ**.

Có ít nhất hai lựa chọn rõ ràng:

**Cách A — Chỉ cần danh sách khóa:** dùng `map` sang khóa rồi `distinct`.

~~~java
List<String> uniqueSkus = products.stream()
    .map(Product::sku)
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

Đoạn này giả định `Product` là record có accessor `sku()` như mục 5. Kết quả là `List<String>`; các thông tin khác của sản phẩm không còn được giữ.

**Cách B — Cần giữ cả đối tượng và chọn bản ghi đầu tiên theo khóa:** thu vào `LinkedHashMap` với merge function giữ giá trị cũ.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// products là List<Product> từ ví dụ record ở mục 5.
Map<String, Product> firstBySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        Function.identity(),
        (first, later) -> first,
        LinkedHashMap::new
    ));

List<Product> uniqueProducts = new ArrayList<>(firstBySku.values());
~~~

Ý nghĩa của bộ collector:

- `Product::sku`: lấy **khóa nhóm**.
- `Function.identity()`: giữ **đối tượng Product** làm giá trị.
- `(first, later) -> first`: khi khóa trùng, **giữ bản ghi đã gặp trước**.
- `LinkedHashMap::new`: bảo toàn thứ tự chèn khóa trong kết quả ở trường hợp thu thập tuần tự từ List có thứ tự.

Nếu bản ghi **mới nhất** mới là bản đúng, cần xác định trường thời gian hoặc phiên bản và chính sách chọn dữ liệu. Không nên mặc định “bản đầu tiên” là đúng về nghiệp vụ.

Tránh mẹo dùng `filter` với một `HashSet` mutable đặt ngoài như `filter(item -> seen.add(item.getId()))`. Đó là predicate có trạng thái, khó lý giải khi chạy song song và đi ngược hướng dẫn sử dụng hàm hành vi không phụ thuộc trạng thái thay đổi bên ngoài. Khi cần loại theo khóa, collector hoặc thuật toán có khóa được định nghĩa rõ ràng sẽ dễ bảo trì hơn.

## 9. Các trường hợp đặc biệt: null, kiểu nguyên thủy, dữ liệu không giới hạn

### 9.1. distinct có thể giữ một null

Không phải nguồn Stream nào cũng cấm null. Với một Stream đối tượng chứa nhiều `null`, `distinct()` chỉ giữ **tối đa một** giá trị `null`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> values = Arrays.asList(null, "A", null, "A", "B");

List<String> unique = values.stream()
    .distinct()
    .collect(Collectors.toList());

System.out.println(unique); // [null, A, B]
~~~

Ngược lại, `List.of(...)` từ Java 9 **không cho phép null**, nên không dùng `List.of(null, ...)` để tạo nguồn kiểm thử này. Nếu nghiệp vụ muốn bỏ null, đặt `filter(Objects::nonNull)` trước `distinct`.

### 9.2. IntStream và LongStream cũng có distinct

Với Stream giá trị nguyên thủy, không cần tự viết `equals` hoặc `hashCode`:

~~~java
import java.util.Arrays;

int[] unique = Arrays.stream(new int[] {3, 1, 3, 2, 1})
    .distinct()
    .toArray();

System.out.println(Arrays.toString(unique)); // [3, 1, 2]
~~~

`IntStream.distinct()`, `LongStream.distinct()` và `DoubleStream.distinct()` được cung cấp bởi các primitive stream tương ứng. Với `DoubleStream`, cần lưu ý các quy tắc về `NaN` và `+0.0`/`-0.0` theo ngữ nghĩa của API khi xử lý số thực; đừng suy luận đơn giản rằng mọi phép so sánh bằng toán tử `==` đều tương ứng với khử trùng.

### 9.3. Dãy vô hạn có thể làm distinct chờ mãi

~~~java
import java.util.stream.Stream;

List<Integer> three = Stream.iterate(0, n -> (n + 1) % 3)
    .distinct()
    .limit(3)
    .collect(java.util.stream.Collectors.toList());
// [0, 1, 2]
~~~

Nguồn `0, 1, 2, 0, 1, 2, ...` là vô hạn nhưng có **ba** giá trị khác nhau, nên `limit(3)` phía sau `distinct` có thể nhận đủ kết quả và kết thúc.

Ngược lại, pipeline:

~~~java
// Không kết thúc theo cách thông thường: chỉ có 3 giá trị khác nhau.
// Stream.iterate(0, n -> (n + 1) % 3)
//     .distinct()
//     .limit(4)
//     .toList();
~~~

sẽ tiếp tục chờ **giá trị duy nhất thứ tư**, vốn không tồn tại. Với nguồn không giới hạn, cần chứng minh được phép toán kết thúc thực sự có điều kiện dừng, và tính đến bộ nhớ khi số giá trị duy nhất tăng mãi.

## 10. Hiệu năng và Stream song song

Vì `distinct()` là **stateful intermediate operation**, nó thường phải duy trì thông tin về các giá trị đã gặp. Với dữ liệu rất nhiều giá trị khác nhau, bộ nhớ theo dõi trùng lặp có thể tăng đáng kể.

Một mô hình phân tích thường gặp với cấu trúc băm tốt:

- Thời gian xử lý trung bình có thể gần **O(n)** cho `n` phần tử, nếu `hashCode` phân bố tốt và chi phí tính `equals/hashCode` hợp lý.
- Bộ nhớ để ghi nhận giá trị duy nhất thường tăng theo số phần tử **khác nhau**.
- Khi có va chạm băm nhiều, xử lý equality đắt, hoặc khi triển khai cần giữ encounter order, chi phí có thể tăng.

Đây là **ước lượng định hướng**, không phải cam kết độ phức tạp cố định từ hợp đồng API. Cách triển khai, kích thước đầu vào, thứ tự và phép toán tiếp theo đều ảnh hưởng tới chi phí thực tế.

### 10.1. distinct trên parallel Stream

~~~java
List<String> unique = names.parallelStream()
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

Với **Stream có encounter order**, `distinct` trong luồng song song vẫn phải giữ **đại diện xuất hiện đầu**. Để bảo đảm tính stable, triển khai có thể phải phối hợp nhiều nhánh và dựng hàng rào đồng bộ đáng kể, làm giảm lợi ích xử lý song song.

Nếu **thứ tự và đại diện đầu tiên không quan trọng**:

~~~java
List<String> uniqueUnordered = names.parallelStream()
    .unordered()
    .distinct()
    .collect(java.util.stream.Collectors.toList());
~~~

`unordered()` có thể cho phép triển khai tối ưu tốt hơn. Tuy nhiên, không nên áp dụng nếu kết quả cần thứ tự hiển thị hay cần chọn bản ghi đầu tiên trong nhóm. Cũng không nên mặc định rằng `parallelStream()` nhanh hơn: hãy đo bằng benchmark phù hợp với dữ liệu và môi trường của ứng dụng.

### 10.2. Đừng biến distinct thành chỗ phát sinh tác dụng phụ

~~~java
long count = List.of("A", "A", "B").stream()
    .map(value -> {
        System.out.println("Đã thấy: " + value);
        return value;
    })
    .distinct()
    .count();
~~~

Số lần `map` được gọi không nên là điều kiện đúng sai của nghiệp vụ. Stream có quyền tối ưu hóa pipeline khi kết quả cuối không cần đánh giá đầy đủ mọi thao tác trung gian trong một số tình huống. Với `distinct`, phải xác định nhóm tương đương để trả số lượng, nhưng số lần và thứ tự chạy các callback vẫn không phải giao diện để đảm bảo logging hay cập nhật trạng thái. Hãy dùng các phép biến đổi không có tác dụng phụ, còn việc ghi log hoặc I/O nghiệp vụ nên được thiết kế ở ranh giới có thể kiểm soát.

## 11. Bài tập thực hành: danh sách email đăng ký trùng

Hệ thống nhận danh sách email:

~~~java
List<String> emails = List.of(
    "  AN@example.com ",
    "binh@example.com",
    "an@EXAMPLE.com",
    "chi@example.com",
    "binh@example.com"
);
~~~

**Yêu cầu:** Cắt khoảng trắng hai đầu, chuẩn hóa chữ thường theo `Locale.ROOT`, loại trùng và giữ thứ tự xuất hiện của mỗi email sau chuẩn hóa. Sau đó đếm tổng số email hợp lệ theo quy tắc đơn giản là không rỗng. Lưu ý bài tập này chỉ chuẩn hóa kỹ thuật, **không khẳng định** mọi hệ thống email đều coi phần trước dấu `@` là không phân biệt hoa/thường.

**Lời giải (Java 9+):**

~~~java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class UniqueEmailDemo {
    public static void main(String[] args) {
        List<String> emails = List.of(
            "  AN@example.com ",
            "binh@example.com",
            "an@EXAMPLE.com",
            "chi@example.com",
            "binh@example.com"
        );

        List<String> uniqueEmails = emails.stream()
            .map(String::trim)
            .map(email -> email.toLowerCase(Locale.ROOT))
            .filter(email -> !email.isEmpty())
            .distinct()
            .collect(Collectors.toList());

        System.out.println(uniqueEmails);
        System.out.println("Số email khác nhau: " + uniqueEmails.size());
    }
}
~~~

Kết quả:

~~~text
[an@example.com, binh@example.com, chi@example.com]
Số email khác nhau: 3
~~~

**Tự kiểm tra:**

1. Nếu đưa `distinct()` **trước** hai bước chuẩn hóa, kết quả có còn ba email duy nhất không? — **Không**; sự khác nhau về khoảng trắng/chữ hoa tồn tại ở thời điểm so sánh.
2. `distinct()` so sánh hai chuỗi với `==` hay `equals`? — **`equals`**.
3. Hai sản phẩm có cùng `sku` nhưng khác `name` trong `record Product(String sku, String name)` có bị gộp không? — **Không**, record mặc định so sánh cả hai trường.
4. Nếu chỉ ghi đè `equals` mà không bảo đảm `hashCode` nhất quán thì điều gì có thể xảy ra? — Cấu trúc dựa trên băm và thao tác khử trùng có thể xử lý sai.
5. `unordered().distinct()` có bắt buộc chọn bản ghi xuất hiện đầu tiên không? — **Không**.
6. Vì sao `distinct().limit(4)` trên nguồn vô hạn chỉ có ba giá trị duy nhất có thể chạy không kết thúc? — Vì **không bao giờ có giá trị duy nhất thứ tư**.

## 12. Ghi nhớ và hướng áp dụng

`distinct()` là phép toán **loại phần tử trùng** trên Stream, xác định tính trùng của đối tượng theo `equals` và yêu cầu hợp đồng `hashCode` nhất quán. Với Stream có encounter order, nó giữ **đại diện đầu tiên**; với Stream unordered, không dựa vào thứ tự hay đại diện được chọn. Đây là phép toán trung gian **lazy và có trạng thái**, nên cần lưu ý hiệu năng, bộ nhớ và khả năng dừng của pipeline.

Trước khi áp dụng, hãy trả lời bốn câu hỏi: **“Trùng” theo trường nào?**; **lớp có định nghĩa equals/hashCode theo trường đó chưa?**; **cần giữ bản ghi đầu tiên hay bản ghi được chọn theo quy tắc khác?**; và **sau khi loại trùng, cần thứ tự/kích thước kết quả thế nào?**

Khi hiểu rõ những điều này, bạn có thể phối hợp `filter`, `map`, `distinct`, `sorted`, `limit` và `collect` một cách chính xác; với bài toán deduplicate theo khóa phức tạp, grouping hoặc collector tùy chỉnh có thể phù hợp hơn. Các quy tắc về trạng thái, thứ tự và tính ổn định cũng là nền tảng quan trọng khi học `Spliterator`, parallel Stream và Stream Gatherers trong những phần tiếp theo.
