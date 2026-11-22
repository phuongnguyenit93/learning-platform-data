# Dùng cùng quy tắc so sánh cho sort, binarySearch, TreeSet và TreeMap

Một comparator không chỉ quyết định thứ tự hiển thị. Nó còn trả lời hai câu hỏi quan trọng:

1. **Giá trị nào đứng trước hoặc sau giá trị nào?**
2. **Những giá trị nào được xem là cùng hạng khi kết quả compare bằng 0?**

Khi một tập dữ liệu được sắp xếp, tìm kiếm và đưa vào cấu trúc cây có thứ tự, các nơi đó phải hiểu các câu trả lời theo đúng quy tắc đã chọn. Nếu mỗi nơi dùng một quy tắc khác mà không có chủ đích, kết quả có thể trông mâu thuẫn: tìm không thấy dữ liệu, hai bản ghi bị gộp, hoặc một lần put lại thay giá trị cũ thay vì tăng kích thước.

Cách làm dễ kiểm soát là định nghĩa một quy tắc có tên rồi truyền rõ ràng cho các thao tác đang biểu diễn cùng một chỉ mục dữ liệu.

## 1. Vai trò của comparator trong bốn nơi sử dụng

| Nơi sử dụng | Comparator được dùng để làm gì? | Khi compare bằng 0 |
| --- | --- | --- |
| `list.sort(rule)` | Tổ chức lại thứ tự phần tử trong danh sách | Các phần tử hòa nhau vẫn được giữ |
| `Collections.binarySearch(list, key, rule)` | Chọn nửa cần tìm và nhận biết một kết quả phù hợp | Có thể trả một vị trí của phần tử cùng hạng với key |
| `new TreeSet<>(rule)` | Tổ chức cây, tìm, thêm, xóa phần tử | Được xem là cùng phần tử theo thứ tự của cây |
| `new TreeMap<>(rule)` | Tổ chức, tìm và cập nhật theo khóa | Hai khóa được xem là cùng khóa theo thứ tự của cây |

Điểm chung là quan hệ so sánh. Khác biệt là **mỗi cấu trúc làm gì với những giá trị cùng hạng**.

Comparator có thể có nhiều tiêu chí, chiều giảm dần hoặc chính sách null. Các chi tiết đó đều thuộc quy tắc, không phải phần trang trí chỉ dành cho lúc sort.

## 2. Trước hết, đặt tên cho toàn bộ quy tắc

Giả sử có mặt hàng gồm mã và giá:

```java
record Product(String sku, int price) {}
```

Yêu cầu của chỉ mục:

- Giá tăng dần.
- Khi bằng giá, mã tăng dần theo thứ tự của `String`.
- Mã không null trong miền dữ liệu của ví dụ.

Khai báo:

```java
private static final Comparator<Product> ORDER =
        Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);
```

Đây là phần khai báo trong lớp, không phải chương trình độc lập.

Tên `ORDER` đại diện cho **cả hai tiêu chí**, không chỉ cho giá. Nếu đoạn tìm kiếm vô tình bỏ `thenComparing`, nó đã đổi ý nghĩa của kết quả bằng 0: từ cùng giá và cùng mã thành chỉ cần cùng giá.

Dùng `comparingInt` thay cho phép trừ giá giúp tránh tự đưa lỗi tràn số vào comparator.

### Cùng quy tắc không bắt buộc cùng tham chiếu

Hai đối tượng comparator được tạo riêng nhưng đưa ra cùng quan hệ thứ tự trên miền dữ liệu có thể dùng tương đương về hành vi.

Không cần kiểm tra `sortRule == searchRule`. Cũng không thể dựa hoàn toàn vào `sortRule.equals(searchRule)` để xác nhận hai biểu thức lambda mô tả cùng quy tắc.

Dùng chung một hằng có tên giúp giảm nguy cơ lệch cấu hình và giúp người đọc nhìn thấy ý định. Điều quan trọng sau cùng vẫn là **quan hệ thứ tự thực sự**, không phải địa chỉ đối tượng comparator.

## 3. sort tạo ra tiền điều kiện cho binarySearch

### 3.1. Danh sách phải được sắp theo comparator tìm kiếm

Tìm kiếm nhị phân dựa vào khả năng loại bỏ một nửa dữ liệu: khi so phần tử giữa với khóa cần tìm, nó phải tin rằng các giá trị ở mỗi phía tuân theo thứ tự.

Vì vậy, trước khi gọi:

```java
Collections.binarySearch(products, query, ORDER);
```

danh sách phải đang được sắp theo `ORDER`.

Cách dùng rõ ràng:

```java
products.sort(ORDER);
int index = Collections.binarySearch(products, query, ORDER);
```

Các dòng trên là minh họa bên trong phương thức có các biến phù hợp.

Không được sắp theo giá tăng rồi tìm bằng giá giảm, hoặc sắp theo mã nhưng tìm theo giá, nếu danh sách không đồng thời đáp ứng thứ tự của comparator tìm kiếm.

Khi tiền điều kiện không thỏa, kết quả không được bảo đảm. API không hứa luôn ném ngoại lệ để báo rằng bạn đã dùng sai comparator. Xem [hợp đồng Collections.binarySearch với Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T,java.util.Comparator)).

### 3.2. Điều kiện chính xác là “đang có thứ tự phù hợp”

Không phải cứ hai comparator khác nhau là tìm kiếm chắc chắn sai.

Ví dụ, danh sách sắp theo **giá rồi mã** cũng được sắp theo **giá** nếu comparator giá dùng cùng chiều. Tìm kiếm chỉ theo giá có thể hợp lệ về tiền điều kiện.

Nhưng khi đó câu hỏi đã đổi:

- Tìm bằng giá rồi mã: cần một mặt hàng có cả giá và mã cùng hạng.
- Tìm chỉ bằng giá: cần một mặt hàng bất kỳ thuộc hạng giá đó.

Nếu mục đích là tìm đúng mã, dùng comparator chỉ theo giá là sai ý định dù thuật toán tìm kiếm vẫn được cung cấp danh sách có thứ tự hợp lệ.

Vì vậy, hãy kiểm tra cả **thứ tự** và **ý nghĩa khớp**, không chỉ kết luận “binarySearch đã trả chỉ số dương nên mọi thứ đều đúng”.

### 3.3. Không bỏ comparator trong lời gọi tiếp theo

Overload không truyền comparator dùng thứ tự tự nhiên. Nó không nhớ comparator đã được dùng trong một lần sort trước.

```java
List<Integer> numbers = new ArrayList<>(List.of(4, 1, 9));
Comparator<Integer> descending = Comparator.reverseOrder();

numbers.sort(descending);
int index = Collections.binarySearch(numbers, 4, descending);
```

Đoạn này minh họa một cặp thao tác cùng quy tắc.

Không thay lời gọi cuối bằng overload tự nhiên rồi dựa vào việc nó có thể vẫn tình cờ tìm ra số 4 trong một dữ liệu nhỏ. Một kết quả tình cờ không xác nhận tiền điều kiện.

Danh sách không mang theo metadata “tôi được sắp bằng comparator nào”. Bên sử dụng phải duy trì thông tin đó.

## 4. Diễn giải kết quả binarySearch đúng cách

### 4.1. Kết quả không âm là một phần tử cùng hạng

Với `result >= 0`, vị trí đó có phần tử thỏa:

```text
rule.compare(list.get(result), key) == 0
```

Điều này không tự bảo đảm `list.get(result).equals(key)`, bởi comparator có thể cố ý bỏ qua một số khác biệt của đối tượng.

Nếu có nhiều phần tử cùng hạng, API không bảo đảm trả phần tử đầu hoặc cuối của nhóm. Muốn lấy toàn bộ nhóm phải có bước tìm biên hoặc thuật toán phù hợp riêng.

### 4.2. Kết quả âm mã hóa điểm chèn

Nếu không tìm được phần tử cùng hạng:

```text
result = -(insertionPoint) - 1
insertionPoint = -result - 1
```

Điểm chèn là vị trí đặt phần tử để giữ thứ tự theo comparator đang dùng. Trong thứ tự giảm dần, “điểm chèn” vẫn được hiểu theo chiều comparator, không theo độ lớn số học mặc định.

Mẫu xử lý tổng quát:

```java
int result = Collections.binarySearch(products, query, ORDER);

if (result >= 0) {
    Product match = products.get(result);
    System.out.println("Found: " + match);
} else {
    int insertionPoint = -result - 1;
    products.add(insertionPoint, query);
}
```

Đây là đoạn minh họa trong một phương thức. Nhánh thêm chỉ phù hợp khi danh sách cho sửa và chính sách nghiệp vụ muốn thêm query khi chưa có phần tử cùng hạng.

Không dùng trực tiếp kết quả âm làm chỉ số. Kết quả âm cũng không phải luôn là -1: -1 chỉ tương ứng điểm chèn 0.

Với mảng đối tượng, cặp `Arrays.sort(array, rule)` và `Arrays.binarySearch(array, key, rule)` có cùng yêu cầu phối hợp thứ tự; xem [API Arrays.binarySearch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#binarySearch(T%5B%5D,T,java.util.Comparator)).

## 5. TreeSet giữ quy tắc và dùng nó trong suốt vòng đời

Khi tạo:

```java
TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
```

cây lưu comparator và dùng cho những thao tác tiếp theo. Không truyền comparator lần nữa ở `contains`, `add` hoặc `remove`.

Một danh sách đã được sắp không tự làm `TreeSet` hiểu quy tắc của danh sách đó:

```java
TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
orderedSet.addAll(products);
```

Đây là cách thể hiện rõ việc dùng chung quy tắc.

### Hòa thứ tự là trùng theo cây

Nếu comparator chỉ dùng giá, hai sản phẩm khác mã nhưng cùng giá so sánh bằng 0. `TreeSet` xem chúng là cùng phần tử theo thứ tự, nên không giữ cả hai như một danh sách.

Thêm tiêu chí mã thay đổi quan hệ hòa: cùng giá nhưng khác mã được phân biệt.

Tuy nhiên, thêm một tiêu chí bất kỳ chưa chắc làm comparator nhất quán với `equals` của kiểu dữ liệu. Cần đối chiếu toàn bộ định nghĩa của kiểu. Với record `Product` trong ví dụ, so sánh đủ giá và mã không null phù hợp với các thành phần mà record dùng cho `equals`.

Nếu thứ tự không nhất quán với `equals`, hành vi nhận diện phần tử của cây có thể khác hợp đồng tập hợp thông thường dựa trên `equals`. Điều này cần được xử lý ở thiết kế, không che giấu bằng một comparator cố tình trả khác 0 cho mọi lần gọi. Xem [API TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 6. TreeMap áp dụng quy tắc lên khóa

```java
TreeMap<Product, String> labels = new TreeMap<>(ORDER);
```

Ở đây, `Product` là **khóa**, còn `String` là giá trị.

Nếu đặt một `Product` mới có cùng giá và cùng mã theo `ORDER`, nó thuộc cùng khóa thứ tự với khóa đã có. `put` cập nhật giá trị cho ánh xạ đó thay vì tăng số khóa.

Với comparator chỉ dùng giá, hai mã khác nhau nhưng cùng giá cũng có thể cập nhật cùng một ánh xạ. Nếu mục tiêu là một nhãn cho mỗi mặt hàng, đó là dấu hiệu quy tắc khóa chưa đủ chi tiết.

### Không nhầm comparator của khóa với comparator của giá trị

Nếu đổi mô hình thành:

```java
Map<String, Product> bySku;
```

thì quy tắc của một `TreeMap<String, Product>` sẽ áp dụng lên `String` là khóa, không áp dụng lên `Product` là giá trị.

Sắp một danh sách product theo giá và lưu map theo mã là hai chỉ mục khác nhau có thể hoàn toàn hợp lý. “Dùng cùng quy tắc” chỉ có ý nghĩa khi đang biểu diễn cùng một quan hệ trên cùng miền khóa/phần tử; không phải bắt mọi cấu trúc trong ứng dụng dùng một comparator duy nhất.

Các thao tác truy cập theo khóa và vai trò comparator được mô tả trong [API TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

## 7. Chương trình hoàn chỉnh: một quy tắc dùng xuyên suốt

Lưu vào **SharedOrderingDemo.java**. Giá ở đây là số nguyên dùng cho ví dụ thứ tự; chương trình tương thích Java 17 trở lên.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;

public class SharedOrderingDemo {
    record Product(String sku, int price) {}

    private static final Comparator<Product> ORDER =
            Comparator.comparingInt(Product::price)
                    .thenComparing(Product::sku);

    private static List<String> describe(Collection<Product> products) {
        return products.stream()
                .map(product -> product.sku() + ":" + product.price())
                .toList();
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
                new Product("D", 300),
                new Product("B", 200),
                new Product("A", 100),
                new Product("C", 200)));

        products.sort(ORDER);
        System.out.println("Sorted: " + describe(products));

        Product query = new Product("C", 200);
        int found = Collections.binarySearch(products, query, ORDER);
        System.out.println("Found index: " + found);

        Product missing = new Product("X", 200);
        int result = Collections.binarySearch(products, missing, ORDER);
        int insertionPoint = -result - 1;
        System.out.println("Missing result: " + result);
        System.out.println("Insertion point: " + insertionPoint);

        TreeSet<Product> orderedSet = new TreeSet<>(ORDER);
        orderedSet.addAll(products);
        System.out.println("TreeSet: " + describe(orderedSet));
        System.out.println("TreeSet contains C: " + orderedSet.contains(query));
        System.out.println("TreeSet contains X: " + orderedSet.contains(missing));

        TreeMap<Product, String> labels = new TreeMap<>(ORDER);
        for (Product product : products) {
            labels.put(product, "label-" + product.sku());
        }
        String previous = labels.put(new Product("C", 200), "updated");
        System.out.println("TreeMap key order: "
                + describe(labels.navigableKeySet()));
        System.out.println("Previous C label: " + previous);
        System.out.println("Current C label: " + labels.get(query));
        System.out.println("TreeMap size: " + labels.size());

        products.add(insertionPoint, missing);
        System.out.println("After ordered insert: " + describe(products));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SharedOrderingDemo.java
java SharedOrderingDemo
```

Stdout:

```text
Sorted: [A:100, B:200, C:200, D:300]
Found index: 2
Missing result: -4
Insertion point: 3
TreeSet: [A:100, B:200, C:200, D:300]
TreeSet contains C: true
TreeSet contains X: false
TreeMap key order: [A:100, B:200, C:200, D:300]
Previous C label: label-C
Current C label: updated
TreeMap size: 4
After ordered insert: [A:100, B:200, C:200, X:200, D:300]
```

### 7.1. Thứ tự và tìm kiếm

Danh sách được sắp theo giá rồi mã:

```text
A:100 -> B:200 -> C:200 -> D:300
```

Query `C:200` thuộc đúng một hạng trong dữ liệu này, nên tìm được chỉ số 2.

Query `X:200` không có. Nó phải đứng sau `C:200` và trước `D:300`. Điểm chèn là 3, mã hóa thành -4.

Mã chỉ giải mã điểm chèn trực tiếp trong chương trình vì query `X:200` được biết trước là thiếu. Với query tổng quát, phải phân nhánh theo dấu của kết quả như phần trước.

### 7.2. Cây tập hợp và cây ánh xạ

`TreeSet` giữ đủ `B:200` và `C:200` vì mã là tiêu chí phụ. Nó tìm thấy `C:200`, nhưng không coi `X:200` là phần tử đã có chỉ vì cùng giá 200.

`TreeMap` duyệt khóa theo cùng thứ tự. `new Product("C", 200)` là một đối tượng mới nhưng so bằng 0 với khóa tương ứng, nên `put` trả nhãn cũ và thay bằng nhãn mới. Kích thước map vẫn là 4.

### 7.3. Thêm vào danh sách không tự cập nhật cây

Dòng cuối chèn query vào danh sách tại điểm chèn đã tính. Nó vẫn giữ thứ tự danh sách.

`TreeSet` và `TreeMap` là các cấu trúc độc lập trong ví dụ. Việc thêm vào `products` không tự thêm vào chúng. “Cùng comparator” có nghĩa cùng quy tắc, không có nghĩa tự đồng bộ nội dung.

Nếu ứng dụng giữ nhiều chỉ mục cho cùng một dữ liệu, cần thiết kế cách cập nhật chúng nhất quán, hoặc chọn một nguồn dữ liệu để dựng lại các bản chiếu.

## 8. Khớp theo comparator không phải luôn là equals

Để thấy rõ điều này, dùng quy tắc so chuỗi không phân biệt hoa/thường.

Lưu vào **ComparisonEquivalenceDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparisonEquivalenceDemo {
    public static void main(String[] args) {
        Comparator<String> rule = String.CASE_INSENSITIVE_ORDER;
        List<String> names =
                new ArrayList<>(List.of("beta", "ALPHA", "alpha", "Gamma"));
        names.sort(rule);

        String query = "AlPhA";
        int index = Collections.binarySearch(names, query, rule);
        String matched = names.get(index);

        System.out.println("Sorted: " + names);
        System.out.println("Binary search found: " + (index >= 0));
        System.out.println("Comparator match: " + (rule.compare(matched, query) == 0));
        System.out.println("Equals match: " + matched.equals(query));
        System.out.println("List contains exact query: " + names.contains(query));

        TreeSet<String> set = new TreeSet<>(rule);
        set.addAll(names);
        System.out.println("TreeSet size: " + set.size());
        System.out.println("TreeSet contains query: " + set.contains(query));

        TreeMap<String, Integer> counts = new TreeMap<>(rule);
        counts.put("ALPHA", 1);
        Integer previous = counts.put("alpha", 2);
        System.out.println("TreeMap previous: " + previous);
        System.out.println("TreeMap size: " + counts.size());
        System.out.println("TreeMap query value: " + counts.get(query));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparisonEquivalenceDemo.java
java ComparisonEquivalenceDemo
```

Stdout:

```text
Sorted: [ALPHA, alpha, beta, Gamma]
Binary search found: true
Comparator match: true
Equals match: false
List contains exact query: false
TreeSet size: 3
TreeSet contains query: true
TreeMap previous: 1
TreeMap size: 1
TreeMap query value: 2
```

### 8.1. Vì sao không in chỉ số cụ thể của nhóm alpha?

`"ALPHA"` và `"alpha"` cùng hạng theo `String.CASE_INSENSITIVE_ORDER`. Query `"AlPhA"` cũng thuộc hạng đó.

Tìm kiếm có thể trả một vị trí phù hợp trong nhóm, nhưng không cam kết vị trí đầu hay cuối. Chương trình chỉ in những điều được bảo đảm: đã tìm thấy, kết quả compare bằng 0, và kết quả `equals` với query là false.

`List.sort` giữ cả hai phần tử; tính ổn định làm `"ALPHA"` vẫn trước `"alpha"` vì đó là thứ tự tương đối ban đầu. Xem [API List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

### 8.2. Vì sao contains của List và TreeSet khác nhau?

`names.contains(query)` dùng quy tắc bằng nhau của phần tử. Trong dữ liệu không có đúng chuỗi `"AlPhA"`, nên kết quả false.

`TreeSet.contains(query)` dùng quy tắc so sánh của cây, nên true. Hai chuỗi alpha chỉ chiếm một hạng trong cây; cộng với beta và Gamma cho kích thước 3.

Comparator cố ý không nhất quán với `String.equals`. Ví dụ minh họa hệ quả để người học nhận diện; không nên vô tình dùng một tập hợp như vậy rồi kỳ vọng mọi phép toán với các tập hợp dựa trên `equals` sẽ giữ cùng ý nghĩa.

Nếu nghiệp vụ coi các biến thể tên là cùng một khóa, hãy định nghĩa rõ chính sách khóa hoặc biểu diễn chuẩn phù hợp. Đừng để mỗi nơi âm thầm dùng một cách chuẩn hóa khác nhau.

### 8.3. Vì sao put không tạo khóa thứ hai?

`TreeMap` nhận `"ALPHA"` rồi `"alpha"`. Cả hai so bằng 0 theo quy tắc của map, nên lần sau thay giá trị từ 1 sang 2. Query với biến thể `"AlPhA"` lấy được 2.

`String.CASE_INSENSITIVE_ORDER` là quy tắc so chuỗi của Java, không tự trở thành phép sắp xếp ngôn ngữ cho mọi locale. Nếu ứng dụng cần quy tắc ngôn ngữ cụ thể, phải lựa chọn nó rõ ràng rồi áp dụng nhất quán. Xem [API String.CASE_INSENSITIVE_ORDER](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#CASE_INSENSITIVE_ORDER).

## 9. Tinh chỉnh quy tắc có thể đổi cả kết quả khớp

Đặt hai quy tắc:

```java
Comparator<Product> priceOnly =
        Comparator.comparingInt(Product::price);

Comparator<Product> priceThenSku =
        priceOnly.thenComparing(Product::sku);
```

Nếu dữ liệu chứa `B:200` và `C:200`:

| Nơi sử dụng | Chỉ theo giá | Theo giá rồi mã |
| --- | --- | --- |
| Sort danh sách | Hai phần tử hòa nhau | B đứng trước C |
| Binary search `X:200` | Có thể tìm một phần tử giá 200 | Không tìm thấy X:200 |
| TreeSet | B và C cùng một hạng, chỉ giữ một đại diện | Giữ được cả B và C |
| TreeMap dùng Product làm khóa | B và C thuộc cùng khóa thứ tự | Có thể có hai ánh xạ |

Không nên thêm tiêu chí phụ chỉ ở một nơi để “làm đẹp thứ tự” mà không xem nó thay đổi điều kiện bằng 0 ra sao.

Tương tự, thay chiều tăng thành giảm hoặc đổi vị trí null ở đoạn sort nhưng giữ đoạn tìm kiếm cũ có thể phá tiền điều kiện.

Nếu chỉ muốn lấy mọi sản phẩm của một mức giá, tìm một vị trí bằng binary search chưa đủ để lấy cả nhóm. Chọn thao tác tìm khoảng hoặc một chỉ mục theo giá phù hợp với mục tiêu đó.

## 10. Những thay đổi làm thứ tự không còn hợp lệ

### 10.1. Sửa danh sách sau khi sort

Sau khi có thứ tự, các thao tác như thêm vào cuối một phần tử phải đứng giữa, đổi một phần tử ở vị trí bất kỳ, hoặc `shuffle` có thể làm mất tiền điều kiện.

Các lựa chọn:

- Tính vị trí chèn bằng cùng comparator.
- Sắp lại trước khi tìm kiếm.
- Dùng cấu trúc duy trì thứ tự khi yêu cầu thay đổi thường xuyên.

Không cần sắp lại nếu thao tác thực sự giữ thứ tự, nhưng phải có lý do rõ ràng cho bảo đảm đó.

### 10.2. Sửa thuộc tính làm khóa so sánh

Một danh sách chưa đổi vị trí vẫn có thể mất thứ tự nếu giá bên trong đối tượng bị sửa.

Với cây, vấn đề còn xuất hiện ở vị trí đã tổ chức của phần tử/khóa. Cây không tự phát hiện việc một field thay đổi rồi chuyển nút sang chỗ mới.

Đối tượng khóa không cho sửa các trường quyết định thứ tự thường dễ quản lý. Nếu cần cập nhật trường đó, một cách là xóa khi giá trị cũ còn đúng, tạo đối tượng mới và thêm lại. Record `Product` với `String` và `int` trong chương trình giúp tránh việc sửa trực tiếp các thành phần.

### 10.3. Sửa cấu hình comparator

Comparator đọc một bảng trọng số hoặc một cờ chiều sắp xếp đang thay đổi cũng có thể làm quy tắc khác đi mà collection không đổi.

Tránh biến comparator của một cây đang dùng thành một quy tắc khác giữa chừng. Nếu chính sách thứ tự thay đổi, dựng lại cấu trúc theo quy tắc mới hoặc thực hiện quá trình chuyển đổi có kiểm soát.

Đa luồng làm những vấn đề này nghiêm trọng hơn. Dùng chung comparator không cung cấp đồng bộ cho danh sách, TreeSet hoặc TreeMap.

## 11. Lưu ý khi tạo bản sao và chuyển cấu trúc

### 11.1. Constructor không luôn kế thừa comparator của nguồn

Các constructor nhận nguồn tổng quát không thể suy ra comparator từ thứ tự phần tử:

```java
// Product không triển khai Comparable.
// Không dùng cách này để kỳ vọng kế thừa ORDER của một List:
// TreeSet<Product> set = new TreeSet<>(products);
```

Constructor `TreeSet(Collection)` dùng thứ tự tự nhiên. Constructor `TreeSet(SortedSet)` có hợp đồng riêng để giữ thứ tự của sorted set nguồn.

Tương tự:

- `TreeMap(Map)` tạo theo thứ tự tự nhiên của khóa.
- `TreeMap(SortedMap)` dùng thứ tự của sorted map nguồn.

Overload được chọn dựa trên kiểu tĩnh của đối số, nên hãy đọc rõ constructor đang gọi. Cách minh bạch trong ví dụ là tạo cây với `ORDER` rồi đưa dữ liệu vào.

### 11.2. List lấy từ cây không mang theo comparator

`new ArrayList<>(orderedSet)` nhận các phần tử theo thứ tự iterator của cây tại thời điểm sao chép, nhưng bản thân list không lưu comparator của cây.

Khi dùng binary search trên list đó, phải truyền lại quy tắc phù hợp. Có thể lấy quy tắc từ `sortedSet.comparator()` hoặc `sortedMap.comparator()`; kết quả null của các phương thức này biểu thị thứ tự tự nhiên.

Đừng diễn giải null đó thành một chính sách “null đứng đầu/cuối” cho dữ liệu.

### 11.3. TreeMap theo khóa không giữ thứ tự giá trị

Một danh sách lấy từ `treeMap.values()` đi theo thứ tự khóa của map. Nó không tự được sắp theo một comparator riêng của các giá trị.

Chỉ dùng binary search theo giá trị nếu bản dữ liệu hiện tại thực sự đáp ứng thứ tự đó, hoặc đã được sắp riêng theo quy tắc giá trị cần tìm.

## 12. Kiểm tra và chẩn đoán

Một kiểm tra hữu ích cho tiền điều kiện danh sách là kiểm tra mọi cặp kề nhau:

```java
// Phương thức minh họa, đặt trong một lớp có import phù hợp.
static <T> boolean isSorted(
        List<T> values, Comparator<? super T> rule) {
    for (int i = 1; i < values.size(); i++) {
        if (rule.compare(values.get(i - 1), values.get(i)) > 0) {
            return false;
        }
    }
    return true;
}
```

Cách này đánh giá thứ tự hiện tại theo comparator được truyền. Nó không tự chứng minh comparator đúng với mọi bộ ba hoặc ổn định trước thay đổi đồng thời. Với danh sách liên kết lớn, cách truy cập lặp theo chỉ số cũng cần xem lại về chi phí; đoạn mã tập trung vào minh họa điều kiện thứ tự.

Khi gặp kết quả bất thường, rà theo thứ tự:

1. Comparator thật sự được truyền vào sort và search là gì?
2. Có bỏ tiêu chí phụ, đảo chiều hoặc đổi null policy ở một nơi không?
3. Query có đủ dữ liệu của toàn bộ khóa so sánh không?
4. Danh sách có bị thêm, sửa, đảo hoặc thay field sau khi sắp không?
5. Kết quả tìm là bằng 0 theo comparator hay bằng nhau theo equals?
6. Cây đang dùng comparator nào, và constructor nào đã được gọi?
7. Có đang mong cây giữ nhiều phần tử mà comparator coi cùng hạng không?

Nếu chỉ biết mã sản phẩm nhưng thứ tự là giá rồi mã, không thể tùy ý gán một giá giả cho query rồi xem đó là truy vấn theo mã. Chọn chỉ mục theo mã, chẳng hạn một map dùng mã làm khóa, hoặc tìm theo điều kiện phù hợp.

## 13. Bài tập tự kiểm tra

1. Sắp danh sách số theo chiều giảm dần, rồi viết lời gọi binary search tương ứng. Giải thích vì sao overload tự nhiên không nhớ quy tắc sort.
2. Với `priceThenSku`, tính kết quả âm và điểm chèn của một sản phẩm có cùng giá nhưng mã chưa có.
3. Dùng `priceOnly` cho danh sách đã sắp bằng `priceThenSku`: tiền điều kiện có thể còn đúng, nhưng ý nghĩa “tìm thấy” thay đổi thế nào?
4. Dự đoán kích thước của List, TreeSet và TreeMap khi có hai mặt hàng khác mã nhưng cùng giá, với từng comparator.
5. Sao chép TreeSet sang ArrayList. Nêu hai thông tin cần giữ để binary search đúng sau khi sao chép.
6. Mô tả cách cập nhật giá của một khóa đang nằm trong TreeMap mà không để cấu trúc tiếp tục dựa trên khóa so sánh cũ.

Mục tiêu là giữ rõ một chuỗi hợp đồng: **quy tắc tạo thứ tự, tiền điều kiện của tìm kiếm, quan hệ khớp bằng 0 và cách cấu trúc nhận diện phần tử hoặc khóa**. Khi thay đổi quy tắc, cần đánh giá lại cả chuỗi thay vì chỉ quan sát thứ tự in ra.
