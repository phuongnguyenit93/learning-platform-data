# Hai đối tượng equals() false nhưng Comparator trả về 0

## 1. Vấn đề: “khác nhau” theo equals nhưng “tương đương” theo thứ tự

Trong Java, hai cách kiểm tra sau có thể cho kết quả khác nhau:

- `a.equals(b)`: hai đối tượng có **bằng nhau theo hợp đồng bình đẳng của lớp** hay không?
- `comparator.compare(a, b) == 0`: hai đối tượng có **ngang hạng (tương đương) theo tiêu chí sắp xếp** hay không?

Ví dụ hai sản phẩm cùng mã `"P-01"` nhưng khác phiên bản `"red"` và `"blue"`. Nếu phương thức `equals` xem cặp **(mã, phiên bản)** là danh tính, hai sản phẩm đó **không bằng nhau**. Nhưng nếu comparator chỉ xét **mã**, nó sẽ trả về `0` vì cả hai cùng `"P-01"`.

~~~text
a = Product(sku="P-01", variant="red")
b = Product(sku="P-01", variant="blue")

a.equals(b)                   -> false
compareBySku.compare(a, b)    -> 0
~~~

**Không có mâu thuẫn cú pháp:** hai phép so sánh đang trả lời hai câu hỏi khác nhau. Tuy nhiên, sự khác biệt có hậu quả lớn trong các collection có thứ tự như `TreeSet` và `TreeMap`, vì chúng dùng **kết quả so sánh thứ tự bằng 0** để nhận biết phần tử/khóa trùng nhau.

## 2. equals và Comparator định nghĩa hai quan hệ riêng

`equals(Object)` tuân hợp đồng bình đẳng của `Object`: phản xạ, đối xứng, bắc cầu, nhất quán và `x.equals(null) == false` với `x` khác `null`. Khi ghi đè `equals`, lớp cũng cần ghi đè `hashCode` tương thích: hai đối tượng bằng nhau phải có cùng mã băm.

`Comparator<T>` định nghĩa **một thứ tự** trên các đối tượng kiểu `T`. Kết quả âm nghĩa là đứng trước, kết quả dương nghĩa là đứng sau, còn `0` nghĩa là hai đối tượng **không phân biệt được theo thứ tự mà comparator đã chọn**. Nó không tự gọi `equals` để kiểm tra liệu hai đối tượng có giống nhau ở mọi trường hay không.

| Tình huống | equals | Comparator | Diễn giải |
| --- | --- | --- | --- |
| Cùng sku, khác variant; equals xét cả hai, comparator chỉ xét sku | false | 0 | Khác đối tượng theo giá trị đầy đủ, ngang hạng khi xếp theo sku |
| Cùng sku và variant | true | 0 | Bình đẳng và tương đương thứ tự trùng nhau |
| Khác sku | false | Âm hoặc dương | Comparator phân biệt được theo sku |
| Comparator xét (sku, variant), equals cũng xét (sku, variant) | false khi khác variant | Khác 0 khi khác variant | Hai quan hệ được thiết kế nhất quán |

Java khuyến nghị comparator có thứ tự **nhất quán với equals** khi dùng trong `SortedSet`/`SortedMap`: 

~~~text
compare(a, b) == 0    khi và chỉ khi    a.equals(b) == true
~~~

Đây là điều kiện **đồng nhất quan hệ tương đương**, không phải yêu cầu mọi comparator trong mọi ngữ cảnh đều phải xét toàn bộ trường của đối tượng. Một comparator dùng để **nhóm, sắp xếp hiển thị hoặc xếp theo khóa phụ** có thể chủ đích trả về 0 cho hai đối tượng `equals` khác nhau. Chỉ cần hiểu rằng khi đưa comparator đó vào `TreeSet`/`TreeMap`, bạn đang áp dụng một định nghĩa khác về “khóa trùng”.

Một thứ tự hợp lệ còn cần tuân tính đổi chiều dấu, tính bắc cầu và sự nhất quán của nhóm kết quả bằng 0. Không thể chữa nhầm lẫn về bình đẳng bằng một comparator tùy tiện vi phạm hợp đồng thứ tự.

## 3. Vì sao TreeSet coi hai đối tượng khác nhau là một?

`HashSet` sử dụng `hashCode` kết hợp với `equals` để quản lý phần tử. Trong khi đó, `TreeSet` sử dụng **thứ tự tự nhiên** (`Comparable`) hoặc **comparator được cung cấp** để sắp xếp và xác định hai phần tử có trùng nhau trong cây hay không.

Giả sử:

~~~text
a.equals(b) == false
comparator.compare(a, b) == 0
~~~

Nếu thêm `a` trước rồi thêm `b`:

1. `TreeSet` chèn `a`.
2. Khi xét `b`, comparator trả về `0` so với phần tử khóa tương ứng. `TreeSet` coi `b` là tương đương với phần tử đã có và không thêm một phần tử thứ hai.
3. `set.size()` vẫn bằng `1`.
4. `set.contains(b)` có thể trả về `true` mặc dù `a.equals(b)` là `false`: phép tra cứu của cây dựa vào comparator.

Khi comparator không nhất quán với `equals`, Java vẫn có thể thực thi những thao tác theo quy tắc so sánh đã cho, nhưng `TreeSet` **không còn giữ đúng kỳ vọng của hợp đồng `Set` tổng quát về bình đẳng phần tử**. Đây là nguyên nhân của nhiều lỗi dữ liệu bị “mất” khi chuyển từ `HashSet` sang `TreeSet`.

Đặc biệt, **kết quả `contains(b)` không chứng minh đã có đúng đối tượng `b` trong cây**. Nó chỉ cho biết có một phần tử được comparator xem là tương đương với `b`.

## 4. Ví dụ Java 17 chạy được với TreeSet và TreeMap

Chương trình dùng một `record Product` với hai thành phần `sku` và `variant`. Record tự sinh `equals` và `hashCode` dựa trên **cả hai thành phần**. Comparator `BY_SKU` chỉ so `sku`; comparator `BY_SKU_AND_VARIANT` so tiếp `variant` khi sku giống nhau.

Lưu thành **ComparatorZeroDemo.java**:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorZeroDemo {
    record Product(String sku, String variant) {
        Product {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(variant, "variant");
        }
    }

    static final Comparator<Product> BY_SKU =
            Comparator.comparing(Product::sku);

    static final Comparator<Product> BY_SKU_AND_VARIANT =
            Comparator.comparing(Product::sku)
                    .thenComparing(Product::variant);

    public static void main(String[] args) {
        Product red = new Product("P-01", "red");
        Product blue = new Product("P-01", "blue");
        Product other = new Product("P-02", "black");

        System.out.println("equals red/blue: " + red.equals(blue));
        System.out.println("compare by sku zero: "
                + (BY_SKU.compare(red, blue) == 0));
        System.out.println("compare by full key zero: "
                + (BY_SKU_AND_VARIANT.compare(red, blue) == 0));

        Set<Product> hash = new HashSet<>();
        hash.add(red);
        hash.add(blue);
        System.out.println("HashSet size: " + hash.size());

        Set<Product> bySkuSet = new TreeSet<>(BY_SKU);
        System.out.println("TreeSet add red: " + bySkuSet.add(red));
        System.out.println("TreeSet add blue: " + bySkuSet.add(blue));
        System.out.println("TreeSet add other: " + bySkuSet.add(other));
        System.out.println("TreeSet size: " + bySkuSet.size());
        System.out.println("TreeSet contains blue: "
                + bySkuSet.contains(blue));
        System.out.println("TreeSet contains red: "
                + bySkuSet.contains(red));

        Map<Product, String> map = new TreeMap<>(BY_SKU);
        map.put(red, "red-value");
        map.put(blue, "blue-value");
        System.out.println("TreeMap size: " + map.size());
        System.out.println("TreeMap get red: " + map.get(red));
        System.out.println("TreeMap get blue: " + map.get(blue));

        Set<Product> fullSet = new TreeSet<>(BY_SKU_AND_VARIANT);
        fullSet.add(red);
        fullSet.add(blue);
        System.out.println("Full-key TreeSet size: " + fullSet.size());

        Map<Product, String> fullMap =
                new TreeMap<>(BY_SKU_AND_VARIANT);
        fullMap.put(red, "red-value");
        fullMap.put(blue, "blue-value");
        System.out.println("Full-key TreeMap size: " + fullMap.size());
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac ComparatorZeroDemo.java
java ComparatorZeroDemo
~~~

Kết quả chuẩn:

~~~text
equals red/blue: false
compare by sku zero: true
compare by full key zero: false
HashSet size: 2
TreeSet add red: true
TreeSet add blue: false
TreeSet add other: true
TreeSet size: 2
TreeSet contains blue: true
TreeSet contains red: true
TreeMap size: 1
TreeMap get red: blue-value
TreeMap get blue: blue-value
Full-key TreeSet size: 2
Full-key TreeMap size: 2
~~~

### Giải thích kết quả từng bước

- `red.equals(blue)` là `false`: record so cả `sku` và `variant`; trường `variant` khác nhau.
- `BY_SKU.compare(red, blue) == 0` là `true`: comparator chỉ nhìn vào `sku`. Khi thêm `thenComparing(Product::variant)`, hai khóa được phân biệt nên kết quả **khác 0**.
- `HashSet` giữ cả `red` lẫn `blue` vì chúng khác nhau theo `equals`; kích thước bằng `2`.
- `TreeSet` với `BY_SKU` chấp nhận `red` nhưng từ chối lần thêm `blue`, vì cả hai tương đương theo thứ tự. `other` có sku khác nên được thêm. Kích thước cũng là `2`, nhưng **tập phần tử khác với HashSet**: hai phần tử ở đây là `red` và `other`.
- `TreeSet.contains(blue)` trả `true` vì có `red` cùng sku; kết quả đó không khẳng định đối tượng `blue` đã được chèn thành công.
- `TreeMap` coi hai `Product` cùng sku là một khóa. `put(blue, "blue-value")` cập nhật giá trị của mục đã được tạo bằng `red`, khiến kích thước còn `1`. Khi truy vấn theo `red` hoặc `blue`, đều nhận `"blue-value"`.
- Comparator đầy đủ `BY_SKU_AND_VARIANT` phân biệt cả hai, nên `TreeSet` và `TreeMap` cho phép giữ riêng hai mục.

Ví dụ không đưa các trường mutable vào khóa; record có hai trường `String` là bất biến. Nhờ đó, kết quả không bị ảnh hưởng bởi việc sửa khóa sau khi chèn.

## 5. TreeMap xử lý “trùng khóa” theo comparator thế nào?

Tương tự `TreeSet`, `TreeMap` sử dụng comparator (hoặc thứ tự tự nhiên của khóa) để tổ chức cây và tìm một khóa tương đương. Nếu `compare(k1, k2) == 0`, hai khóa được coi là cùng vị trí tra cứu. Khi `put(k2, value2)` sau `put(k1, value1)`, thao tác thông thường cập nhật **giá trị cho khóa tương đương** thay vì tạo mục thứ hai.

Hệ quả:

| Thao tác | Comparator chỉ xét sku | Ý nghĩa |
| --- | --- | --- |
| `put(red, "red-value")` | Thêm mục sku P-01 | Giá trị ban đầu |
| `put(blue, "blue-value")` | Cập nhật mục cùng sku | Không tạo khóa thứ hai |
| `size()` | 1 | Chỉ một lớp tương đương theo sku |
| `get(red)` | `"blue-value"` | Giá trị đã cập nhật |
| `get(blue)` | `"blue-value"` | Cùng lớp tương đương theo comparator |

Điều này nguy hiểm nếu nghiệp vụ cần phân biệt từng `variant`. Thao tác ghi có thể vô tình thay thế dữ liệu trước đó dù `equals` cho biết hai khóa khác nhau. Nếu thực sự muốn mỗi sku chỉ có **một** bản ghi, comparator theo sku có thể phù hợp, nhưng lúc đó nên mô hình hóa khóa trực tiếp là `String sku` hoặc một kiểu khóa chỉ chứa sku để quy tắc dễ hiểu hơn.

Đừng dựa vào thứ tự lặp để phân biệt hai khóa có comparator trả về 0: theo chính sách của cây, chúng vốn là một mục. Muốn lưu nhiều phiên bản dưới cùng sku, có thể dùng `Map<String, List<Product>>`, `Map<String, Set<Product>>` hoặc khóa ghép gồm `(sku, variant)` theo nhu cầu nghiệp vụ.

## 6. Khi nào comparator trả về 0 cho đối tượng equals false là có chủ ý?

Không phải comparator như vậy luôn là lỗi. Một comparator xếp hạng học viên **chỉ theo điểm** có thể coi hai học viên cùng điểm là ngang hạng, dù họ là hai người khác nhau theo `equals`. Khi chỉ dùng comparator để nhóm hoặc sắp xếp danh sách theo điểm, việc ngang hạng có ý nghĩa rõ ràng.

Ví dụ:

~~~java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
~~~

Đây là **khai báo minh họa** với lớp `Student` giả định có phương thức `score()`, không phải chương trình độc lập. Nó cho `0` khi hai học viên cùng điểm. Nếu dùng với `List.sort(byScore)`, danh sách vẫn chứa cả hai học viên; phép sắp xếp không tự xóa phần tử. Nhưng nếu chuyển danh sách đó vào `TreeSet<>(byScore)`, tập sẽ chỉ giữ một phần tử trong mỗi nhóm được xem là tương đương theo điểm.

Tương tự, `String.CASE_INSENSITIVE_ORDER.compare("Java", "java") == 0`, trong khi `"Java".equals("java")` là `false`. Comparator không phân biệt chữ hoa/thường có thể phù hợp cho sắp xếp hiển thị hoặc tìm kiếm không phân biệt hoa/thường, nhưng `TreeSet` dùng comparator đó sẽ không giữ cả hai chuỗi như hai phần tử riêng biệt.

Do đó, trước khi sử dụng một comparator hãy tự hỏi: **tôi đang sắp xếp để hiển thị, đang gom nhóm theo một tiêu chí, hay đang định nghĩa danh tính duy nhất của phần tử/khóa trong một collection có thứ tự?** Ba mục đích này có thể cần ba chính sách khác nhau.

## 7. Cách thiết kế Comparator đúng khi dùng TreeSet/TreeMap

### 7.1. Thêm khóa phụ để phân biệt đối tượng cần giữ riêng

Nếu `equals` của `Product` xét sku và variant, nên dùng:

~~~java
Comparator<Product> byFullKey =
        Comparator.comparing(Product::sku)
                .thenComparing(Product::variant);
~~~

Đây là **biểu thức khai báo comparator trong ngữ cảnh có kiểu Product như chương trình chính**, không phải chương trình độc lập. Khi cả hai chuỗi bằng nhau thì `compare == 0`; với record `Product` đã cho, điều đó cũng đồng nghĩa `equals == true`. Khóa phụ khiến những sản phẩm khác phiên bản không bị nhập thành một mục.

Nếu `equals` còn so nhiều trường hơn, comparator muốn nhất quán phải bảo đảm **không trả 0 cho hai đối tượng mà equals xem là khác nhau**, và cũng không tách hai đối tượng bằng nhau thành hai hạng. Vì thế không thể tự ý chọn một khóa phụ ngẫu nhiên mà bỏ qua những trường bình đẳng thực tế.

### 7.2. Dùng đúng loại collection theo hợp đồng mong muốn

- Cần nhận diện phần tử bằng `equals` và không cần duy trì thứ tự sắp: sử dụng `HashSet`/`HashMap` với `equals` và `hashCode` được cài đặt đúng.
- Cần phần tử/khóa được duyệt theo thứ tự, đồng thời phân biệt đầy đủ các đối tượng theo `equals`: sử dụng `TreeSet`/`TreeMap` với comparator nhất quán với `equals`.
- Cần giữ tất cả đối tượng nhưng hiển thị theo một thuộc tính: lưu trong `List` rồi `sort` bằng comparator theo thuộc tính đó; việc sắp danh sách không loại bỏ các phần tử ngang hạng.
- Cần nhóm nhiều đối tượng theo một thuộc tính: dùng cấu trúc ánh xạ từ thuộc tính nhóm tới một danh sách/tập các phần tử, thay vì dùng một `TreeMap` một-giá-trị rồi vô tình ghi đè nhóm.

`TreeSet` và `TreeMap` yêu cầu comparator cung cấp thứ tự ổn định, đổi chiều đúng dấu và có tính bắc cầu. Việc thêm tie-breaker phải giữ được các tính chất này; `Comparator.comparing(...).thenComparing(...)` với các khóa có thứ tự chuẩn thường dễ kiểm chứng hơn logic thủ công.

### 7.3. Giữ khóa sắp xếp ổn định

Nếu sửa trường tham gia comparator sau khi đưa đối tượng vào `TreeSet` hoặc làm khóa `TreeMap`, cây không tự tái cấu trúc theo giá trị mới. Có thể xảy ra lỗi `contains`, `get` hoặc việc duyệt không còn theo thứ tự mong muốn. Hãy dùng khóa bất biến, hoặc xóa khóa khỏi cấu trúc trước khi thay đổi rồi chèn lại dưới trạng thái mới.

Lưu ý phân biệt: `HashSet` dựa vào tính ổn định của `equals`/`hashCode`; `TreeSet` còn dựa vào tính ổn định của tiêu chí so sánh thứ tự. Một lớp có mã băm ổn định nhưng comparator đọc một trường thay đổi vẫn có rủi ro trong `TreeSet`.

## 8. Những lỗi thường gặp

### Lỗi 1: Giả định TreeSet dùng equals để kiểm tra trùng

Khi `comparator.compare(a, b) == 0`, `TreeSet` xem hai phần tử là tương đương dù `a.equals(b)` là `false`. Kiểm tra `set.contains(b)` có thể trả `true` trong tình huống chưa từng chèn `b` thành công.

### Lỗi 2: Chỉ so khóa chính khi khóa thực tế gồm nhiều trường

Nếu một bản ghi định danh bằng `(userId, orderId)` mà comparator chỉ so `userId`, các đơn hàng của cùng một người dùng sẽ bị gom thành một khóa. Hãy định nghĩa rõ khóa ghép và áp dụng `thenComparing` theo thứ tự ưu tiên thích hợp.

### Lỗi 3: Cố ép comparator trả 1 khi hai đối tượng khác tham chiếu

Một cách “chữa cháy” như `if (a != b) return 1;` không bảo đảm dấu đổi chiều: với hai đối tượng khác nhau có thể cả `compare(a,b)` và `compare(b,a)` đều dương. Đây là vi phạm hợp đồng Comparator. Cần một tiêu chí phụ **có thứ tự xác định**, không phải giá trị trả về tùy tiện.

### Lỗi 4: Thêm tham số ngẫu nhiên hoặc thời gian vào kết quả

Nếu comparator trả kết quả khác nhau cho cùng cặp đối tượng qua các lần gọi, cây sắp xếp có thể không tìm đúng vị trí lưu. Tiêu chí thứ tự phải nhất quán theo trạng thái được phép của đối tượng, và tốt nhất là dựa trên khóa bất biến.

### Lỗi 5: Dùng comparator theo nhóm rồi cho rằng mọi phần tử đã được giữ nguyên

`TreeSet` chỉ lưu một đại diện cho mỗi nhóm tương đương theo comparator. `TreeMap` chỉ lưu một mục cho mỗi khóa tương đương. Muốn giữ toàn bộ thành viên một nhóm, hãy dùng `List`, hoặc `Map<GroupKey, List<Member>>` để biểu diễn rõ quan hệ một–nhiều.

## 9. Kiểm thử trước khi đưa Comparator vào SortedSet hoặc SortedMap

Với các giá trị khác nhau về nghiệp vụ, thử những ca sau:

1. Chọn hai đối tượng `a`, `b` mà `!a.equals(b)`. So kết quả `compare(a,b)`; nếu là `0`, xác định xem việc coi chúng là một khóa trong cây có chủ ý hay không.
2. Chọn hai đối tượng bằng nhau theo `equals`. Nếu cần tương thích hợp đồng `Set`/`Map`, xác nhận `compare(a,b) == 0`.
3. Thử `TreeSet.add(a)`, `TreeSet.add(b)`, `size()` và `contains(b)`; đừng suy luận sự tồn tại riêng biệt chỉ dựa vào `contains`.
4. Thử `TreeMap.put(a,v1)`, `put(b,v2)`, `size()` và `get`; xác định rõ có thể ghi đè giá trị vì comparator coi hai khóa là một hay không.
5. Thêm tie-breaker cần thiết và kiểm tra lại với các đối tượng cùng khóa chính nhưng khác khóa phụ.
6. Kiểm tra tính bắc cầu, đổi chiều dấu và ổn định của comparator; đặc biệt với giá trị biên, thuộc tính nullable và khóa mutable.
7. Kiểm tra mọi trường hợp `null`: `Comparator.nullsFirst`/`nullsLast` khi muốn hỗ trợ đối tượng hoặc khóa `null` phù hợp với collection, nhưng lưu ý **TreeMap/TreeSet có thể không chấp nhận null tùy comparator**; phải kiểm tra chính sách thực tế thay vì suy đoán.

**Ghi nhớ:** `a.equals(b) == false` và `comparator.compare(a,b) == 0` hoàn toàn có thể cùng đúng vì hai phép so sánh có mục đích khác nhau. Nhưng khi comparator được dùng bởi `TreeSet` hoặc `TreeMap`, **0 nghĩa là cùng một phần tử/khóa theo cây**. Nếu cần giữ hai đối tượng như hai giá trị riêng biệt, hãy định nghĩa tiêu chí thứ tự phù hợp với `equals`, thường bằng cách thêm các khóa phụ cần thiết.