# Stream.min(), Stream.max() và Comparator trong Java

Trong **Java Stream API**, hai thao tác kết thúc **min()** và **max()** dùng để tìm một phần tử nhỏ nhất hoặc lớn nhất **theo quy tắc so sánh được truyền vào**, thay vì nhất thiết tìm số nhỏ nhất hoặc chuỗi lớn nhất theo một nghĩa cố định.

Với object stream, chữ ký là:

~~~java
Optional<T> min(Comparator<? super T> comparator);
Optional<T> max(Comparator<? super T> comparator);
~~~

Kết quả dùng **Optional<T>** vì Stream có thể rỗng, không có phần tử để chọn. **Comparator** quyết định thứ tự: nếu đổi Comparator, cùng một Stream có thể cho kết quả min/max khác nhau. Bài học giải thích cách dùng, thứ tự tăng/giảm, so sánh nhiều tiêu chí, xử lý trường hợp hòa, null, dữ liệu rỗng, primitive streams, và những lỗi phổ biến. Ví dụ chạy bằng **Java 17+**.

## 1. min() và max() là thao tác kết thúc gì?

Stream thường có ba thành phần: nguồn dữ liệu, các **intermediate operations** như filter/map, và một **terminal operation** thực thi pipeline để cho ra kết quả hoặc side effect.

~~~java
List<Integer> prices = List.of(120, 20, 450);

Optional<Integer> smallest = prices.stream()
    .min(Comparator.naturalOrder());

Optional<Integer> largest = prices.stream()
    .max(Comparator.naturalOrder());
~~~

Đây là các câu lệnh minh họa cần đặt trong phương thức với import tương ứng. Với danh sách trên:

- smallest chứa 20.
- largest chứa 450.
- Stream.min/max kết thúc lượt xử lý và tiêu thụ Stream tương ứng.
- Các phép toán không xóa hoặc sắp xếp lại phần tử của prices.

Điểm cần nhớ: **min và max không phải intermediate operations**. Không thể viết stream.min(...).filter(...) vì min trả Optional<T>, không trả Stream<T>.

### 1.1. Vì sao trả Optional?

Một Stream rỗng không có phần tử tối thiểu hoặc tối đa:

~~~java
Optional<Integer> emptyResult =
    Stream.<Integer>empty().min(Comparator.naturalOrder());

System.out.println(emptyResult.isEmpty()); // true
~~~

Không nên lấy kết quả bằng get() mà chưa xác định Optional có giá trị. Với Optional.empty(), get() ném NoSuchElementException.

Cách xử lý phù hợp:

~~~java
Integer price = products.stream()
    .map(Product::price)
    .min(Integer::compare)
    .orElse(0);
~~~

Ở đây orElse(0) có nghĩa chọn 0 khi rỗng; giá trị mặc định **phải có nghĩa trong nghiệp vụ**. Đừng tự động dùng 0 cho một mức giá tối thiểu nếu 0 sẽ làm người đọc tưởng có một sản phẩm giá 0.

Nếu Stream rỗng là trạng thái không hợp lệ:

~~~java
Product cheapest = products.stream()
    .min(byPrice)
    .orElseThrow(() -> new IllegalStateException(
        "No products to compare"));
~~~

Nếu Stream rỗng hợp lệ, có thể trả Optional<Product> lên caller để caller quyết định hiển thị trạng thái “không có dữ liệu”.

### 1.2. min/max cần duyệt dữ liệu ở mức nào?

Để tìm một phần tử nhỏ nhất/lớn nhất trong một nguồn tổng quát, hệ thống thường cần so sánh các phần tử liên quan trong quá trình giảm (reduction). Không có cơ chế mặc định “nhìn phần tử đầu tiên là đủ” như findFirst. Với nguồn vô hạn và không có giới hạn, min/max có thể không kết thúc.

Với n phần tử và so sánh hằng số, phương pháp giảm để chọn min/max thông thường mất thời gian **O(n)**, có thể giữ một ứng viên nên không bắt buộc thu toàn bộ phần tử thành danh sách mới. Tuy vậy, những intermediate operations trước đó như sorted hoặc distinct có thể tạo thêm chi phí và bộ nhớ.

Đừng tuyên bố mọi Stream.min/max luôn dùng bộ nhớ hằng số hoặc chạy đúng n−1 lần comparator trong mọi pipeline/parallel execution: các tối ưu, nguồn và bộ xử lý song song có thể khác nhau.

## 2. Comparator<T>: quy tắc thứ tự, không phải điều kiện boolean

Comparator<T> là functional interface với phương thức cốt lõi:

~~~java
int compare(T left, T right);
~~~

Giá trị trả về có ý nghĩa theo **dấu**:

- Âm: left đứng **trước** right theo quy tắc so sánh.
- 0: hai phần tử được xem là **bằng nhau theo thứ tự** mà comparator này định nghĩa.
- Dương: left đứng **sau** right.

Không cần trả đúng −1, 0, +1; chỉ dấu mới quan trọng.

Ví dụ:

~~~java
Comparator<Integer> ascending =
    (left, right) -> Integer.compare(left, right);

Comparator<Integer> descending =
    (left, right) -> Integer.compare(right, left);
~~~

Khi dùng ascending, min chọn số nhỏ nhất theo tự nhiên và max chọn số lớn nhất. Khi dùng descending, **thứ tự được đảo**, nên min chọn số lớn nhất theo thứ tự số học gốc.

### 2.1. Không dùng phép trừ int tùy tiện

Cách viết dễ gây tràn số:

~~~java
Comparator<Integer> wrong =
    (left, right) -> left - right;
~~~

Nếu left và right ở hai phía giới hạn int, phép trừ có thể overflow và làm dấu kết quả sai, vi phạm hợp đồng comparator.

Đúng hơn:

~~~java
Comparator<Integer> safe = Integer::compare;
~~~

Với dữ liệu object có một trường int:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

**Comparator.comparingInt** tránh việc phải tự viết phép trừ và cũng giúp mục đích so sánh rõ ràng. Trong trường hợp giá là long hoặc double, có các overload comparingLong và comparingDouble tương ứng.

### 2.2. Hợp đồng Comparator quan trọng

Một comparator đúng phải xác định một quan hệ thứ tự nhất quán, trong đó:

- Tính phản đối xứng về dấu: compare(a,b) và compare(b,a) có dấu ngược nhau.
- Tính bắc cầu: nếu a đứng sau b và b đứng sau c thì a phải đứng sau c, tương tự chiều ngược lại.
- Nếu compare(a,b) bằng 0 thì với mọi z, dấu của compare(a,z) và compare(b,z) phải nhất quán theo hợp đồng Comparator.
- Kết quả nên ổn định khi dữ liệu dùng để so sánh không thay đổi.

Không nên dùng comparator dựa trên random, clock hiện tại hoặc field mutable đang bị cập nhật trong lúc so sánh; min/max có thể trở nên khó đoán hoặc không đúng.

**Comparator.compare(a,b) == 0 không nhất thiết có nghĩa a.equals(b).** Nếu chỉ so sánh price, hai sản phẩm khác mã nhưng cùng giá sẽ được xem là hòa về thứ tự, dù hai đối tượng khác nhau. Điều này đặc biệt quan trọng khi chọn min/max và khi dùng comparator trong TreeSet/TreeMap.

## 3. Comparator.naturalOrder() và reverseOrder()

Đối với kiểu hỗ trợ **Comparable**, có thể dùng thứ tự tự nhiên:

~~~java
List<Integer> values = List.of(7, 3, 10, 4);

int smallest = values.stream()
    .min(Comparator.naturalOrder()).orElseThrow();

int largest = values.stream()
    .max(Comparator.naturalOrder()).orElseThrow();
~~~

Kết quả là 3 và 10.

String cũng implement Comparable<String>, nên với Comparator.naturalOrder(), chuỗi được so sánh theo quy tắc compareTo của String (thứ tự từ điển dựa trên các giá trị UTF-16). **Không** mặc định quy tắc này là thứ tự sắp xếp theo ngôn ngữ tự nhiên hoặc locale.

~~~java
String smallest = Stream.of("zebra", "apple", "pear")
    .min(Comparator.naturalOrder()).orElseThrow();
// "apple"
~~~

Để đảo thứ tự:

~~~java
Comparator<Integer> reversed = Comparator.reverseOrder();

int selected = Stream.of(3, 9, 5)
    .min(reversed)
    .orElseThrow();
// 9, vì 9 đứng "đầu" trong thứ tự đảo.
~~~

### 3.1. Reverse comparator không đổi định nghĩa min/max

Quy tắc căn bản:

**min(comparator)** chọn phần tử đứng đầu nhất theo comparator; **max(comparator)** chọn phần tử đứng cuối nhất theo comparator.

Vì vậy:

~~~java
int a = Stream.of(1, 5, 9)
    .max(Comparator.naturalOrder()).orElseThrow(); // 9

int b = Stream.of(1, 5, 9)
    .max(Comparator.reverseOrder()).orElseThrow(); // 1
~~~

Đừng nghĩ tên max luôn bảo đảm chọn giá trị số học lớn nhất, bất kể comparator ra sao. Comparator mới là nguồn định nghĩa thứ tự.

### 3.2. Comparator.reversed()

Với comparator bất kỳ:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);

Comparator<Product> byPriceDescending =
    byPrice.reversed();
~~~

byPriceDescending định nghĩa giá cao đứng trước giá thấp. Khi gọi max(byPriceDescending), kết quả có thể là **giá thấp nhất** theo thứ tự giá gốc.

Đặc biệt, **min(byPrice.reversed())** tương ứng phần tử giá lớn nhất theo byPrice, trong khi **max(byPrice.reversed())** tương ứng giá nhỏ nhất. Đừng đảo cả comparator lẫn min/max trừ khi logic đã được tính rõ.

## 4. Comparator.comparing: so sánh theo thuộc tính

Trong ứng dụng, phần tử Stream thường là object. Ví dụ record:

~~~java
record Product(String sku, int price, int score) {}
~~~

Nếu muốn tìm sản phẩm rẻ nhất:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);

Optional<Product> cheapest = products.stream()
    .min(byPrice);
~~~

Nếu muốn sản phẩm có điểm đánh giá cao nhất:

~~~java
Comparator<Product> byScore =
    Comparator.comparingInt(Product::score);

Optional<Product> highestRated = products.stream()
    .max(byScore);
~~~

Cả hai thao tác dùng cùng dữ liệu nhưng lựa chọn theo **hai tiêu chí khác nhau**. Đây là lợi ích của comparator: thay quy tắc mà không đổi dữ liệu nguồn.

### 4.1. comparing và comparingInt/Long/Double

Với key là Comparable:

~~~java
Comparator<Product> bySku =
    Comparator.comparing(Product::sku);
~~~

Với key nguyên thủy:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

Nếu Product.price() trả long thì dùng comparingLong; nếu trả double thì comparingDouble, có ngữ nghĩa số thực theo Double.compare. Các primitive-specific factory thường hạn chế boxing/unboxing của khóa khi so sánh so với việc tạo wrapper không cần thiết.

### 4.2. So sánh trường String có thể null

Nếu sku có thể null, Comparator.comparing(Product::sku) sẽ không tự nhiên an toàn: natural order của String không so sánh null như chuỗi hợp lệ. Có thể xác định rõ vị trí cho null:

~~~java
Comparator<Product> byNullableSku =
    Comparator.comparing(
        Product::sku,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Với quy tắc trên, SKU null đứng **sau** các SKU không null khi so sánh tăng dần. Nếu gọi min(), một SKU hợp lệ sẽ được ưu tiên hơn SKU null khi có ít nhất một phần tử không null.

Điều quan trọng là phân biệt:

1. **Một trường thuộc tính của phần tử có thể null**: comparing kết hợp nullsFirst/nullsLast có thể xử lý.
2. **Chính phần tử Stream là null**: dù comparator có thể xử lý, Stream.min/max có thể ném NullPointerException nếu kết quả reduction là null, bởi Optional không chứa giá trị null.

Trong phần lớn thiết kế nghiệp vụ, nên lọc bỏ null element trước khi chọn min/max hoặc xác định rõ validation thay vì mong min/max dùng null như một giá trị kết quả bình thường.

## 5. thenComparing: xử lý hòa bằng tiêu chí phụ

Nếu chỉ so sánh theo giá:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

Hai sản phẩm có cùng price được comparator xem là **bằng nhau về thứ tự** dù khác SKU. Khi Stream.min/max chọn một phần tử trong các phần tử hòa, **không nên phụ thuộc vào việc luôn chọn phần tử đầu tiên** nếu comparator không phân biệt được chúng, nhất là khi thay đổi nguồn hoặc parallel execution.

Để lựa chọn có thể dự đoán, thêm một hoặc nhiều tiêu chí phá hòa:

~~~java
Comparator<Product> byPriceThenSku =
    Comparator.comparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

Quy tắc:

1. So sánh giá trước.
2. Nếu giá khác, kết quả do giá quyết định.
3. Nếu giá bằng nhau, so sánh SKU theo thứ tự tự nhiên.
4. Nếu SKU cũng bằng nhau, comparator vẫn xem hai object hòa về thứ tự.

Với dữ liệu:

~~~text
Book  : 120
Pen   : 20
Lamp  : 450
Case  : 120
Glass : 450
~~~

min(byPriceThenSku) chọn **Pen** (20). max(byPriceThenSku) chọn **Lamp** (450, SKU "Lamp" đứng sau "Glass" theo thứ tự tự nhiên).

**Lưu ý:** chỉ cần deterministic tie-break đến mức nghiệp vụ yêu cầu. Nếu SKU duy nhất cho mỗi sản phẩm, thenComparing(sku) thường đủ. Nếu SKU không duy nhất, có thể thêm mã định danh bền vững khác. Tránh dùng dữ liệu random hoặc thứ tự trả về tình cờ của nguồn làm cơ chế phá hòa.

### 5.1. So sánh nhiều thuộc tính hơn

~~~java
Comparator<Product> order =
    Comparator.comparingInt(Product::score)
        .thenComparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

Quy tắc tăng dần theo score, sau đó price, rồi sku. Gọi max(order) chọn sản phẩm có score cao nhất; trong nhóm cùng score, chọn giá cao nhất; trong nhóm cùng score và price, chọn SKU đứng cuối theo comparator.

Đây không nhất thiết là “đánh giá tốt nhất rồi giá rẻ nhất”. Nếu muốn score cao nhưng **giá thấp** được ưu tiên khi hòa, phải đảo **chỉ** comparator giá:

~~~java
Comparator<Product> bestScoreThenCheapest =
    Comparator.comparingInt(Product::score)
        .thenComparing(
            Comparator.comparingInt(Product::price).reversed())
        .thenComparing(Product::sku);
~~~

Với max(bestScoreThenCheapest), giá **thấp hơn** sẽ được xem là đứng sau trong quy tắc price đảo, nên được ưu tiên trong nhóm cùng score. Đặt tên comparator theo ý định giúp tránh nhầm thứ tự.

### 5.2. reversed đặt ở đâu ảnh hưởng kết quả

~~~java
Comparator<Product> allReversed =
    Comparator.comparingInt(Product::score)
        .thenComparing(Product::sku)
        .reversed();
~~~

reversed cuối cùng đảo **toàn bộ** chuỗi tiêu chí. Nếu bạn chỉ muốn đảo thứ tự SKU mà giữ score tăng, phải viết rõ:

~~~java
Comparator<Product> scoreAscSkuDesc =
    Comparator.comparingInt(Product::score)
        .thenComparing(
            Comparator.comparing(Product::sku).reversed());
~~~

Đây là một khác biệt quan trọng khi sử dụng comparator cho min/max, sorted hoặc cấu trúc dữ liệu có thứ tự.

## 6. Optional<T>: cách sử dụng an toàn

Stream.min/max trên object stream trả Optional<T>. Một số cách xử lý:

~~~java
Optional<Product> candidate = products.stream().min(byPrice);

candidate.ifPresent(product ->
    System.out.println(product.sku()));

Product fallback = candidate.orElse(defaultProduct);

Product required = candidate.orElseThrow(
    () -> new IllegalStateException("No product found"));
~~~

Đây là các đoạn minh họa cần biến products, byPrice và defaultProduct được khai báo hợp lệ.

Chọn chiến lược theo nghĩa nghiệp vụ:

- **orElse**: luôn có một giá trị dự phòng hợp lệ; lưu ý biểu thức đối số được đánh giá khi gọi.
- **orElseGet**: chỉ tính giá trị mặc định khi Optional rỗng, hữu ích nếu fallback đắt.
- **orElseThrow**: khi không có phần tử là tình huống lỗi.
- **ifPresent**, **map**, **flatMap**: tiếp tục xử lý mà không giải bọc một cách thiếu an toàn.
- **Optional.empty()**: là một giá trị kết quả hợp lệ khi bài toán cho phép không tìm được đối tượng.

Không nên dùng Optional.get() ngay sau min/max mà không chứng minh Stream không rỗng. Hãy phân biệt danh sách chưa có sản phẩm và sản phẩm có giá bằng 0; chúng không cùng ý nghĩa.

### 6.1. Filter trước min/max

~~~java
Optional<Product> cheapestAvailable = products.stream()
    .filter(product -> product.price() > 0)
    .min(Comparator.comparingInt(Product::price));
~~~

Nếu không có Product nào có price > 0, kết quả Optional.empty(), dù nguồn ban đầu không rỗng.

Nếu cần chọn phần tử theo một loại trạng thái, hãy lọc trước rồi mới tìm min/max; không nên chọn min toàn nguồn rồi kiểm tra trạng thái sau, vì kết quả có thể khác:

~~~java
// Chọn giá thấp nhất trong nhóm hợp lệ:
products.stream().filter(this::eligible).min(byPrice);
~~~

Đây là đoạn minh họa có phương thức instance eligible và comparator byPrice giả định. Điều quan trọng là **thứ tự nghiệp vụ**: lọc trước tạo tập ứng viên, sau đó chọn phần tử từ tập ứng viên đó.

## 7. So sánh với sorted().findFirst()

Một cách khác để lấy phần tử nhỏ nhất là sắp xếp rồi lấy phần tử đầu:

~~~java
Optional<Product> smallest = products.stream()
    .sorted(byPrice)
    .findFirst();
~~~

Về ý định chọn phần tử nhỏ nhất, có thể tương đương min(byPrice) trong các trường hợp thông thường với comparator nhất quán và không có vấn đề tie/null. Nhưng lựa chọn kỹ thuật khác nhau:

| Cách | Mục tiêu | Chi phí điển hình |
| --- | --- | --- |
| min(comparator) | Chọn một phần tử nhỏ nhất | O(n) lượt so sánh tổng quát, không cần tạo danh sách đã sắp xếp |
| max(comparator) | Chọn một phần tử lớn nhất | O(n) lượt so sánh tổng quát |
| sorted(comparator).findFirst() | Sắp thứ tự rồi lấy đầu | Thường O(n log n) so sánh, có thể cần buffer |
| sorted(comparator).toList() | Lấy toàn bộ theo thứ tự | Sắp toàn bộ, trả List kết quả |
| collect(minBy(comparator)) | Chọn min qua Collector | Hữu ích trong collector downstream |

**Khuyến nghị:** nếu chỉ cần đúng một cực trị, dùng **min/max trực tiếp**. sorted hữu ích khi **thực sự cần danh sách đã sắp thứ tự** hoặc một phần kết quả có yêu cầu bổ sung.

Một điểm khác: sorted trên stream có thứ tự là ổn định theo hợp đồng của Stream.sorted; với các phần tử hòa comparator, việc chọn bằng sorted().findFirst() có thể phản ánh thứ tự nguồn. Không suy diễn quy tắc chọn phần tử hòa của sorted/findFirst sang Stream.min/max; nếu cần lựa chọn xác định xuyên mọi cách thực thi, thêm tie-break rõ ràng.

### 7.1. Không cần sorted để tìm max

~~~java
Product maxPrice = products.stream()
    .max(Comparator.comparingInt(Product::price))
    .orElseThrow();
~~~

Viết sorted(...).reduce(...) hoặc sorted(...).findFirst() chỉ để tìm max thường làm code dài hơn và có thể tốn nhiều công. Ngược lại, nếu cần top 5 sản phẩm với nhiều tiêu chí, việc sắp xếp (hoặc cấu trúc top-k chuyên biệt) mới phù hợp.

## 8. IntStream, LongStream, DoubleStream có min/max không cần Comparator

Object Stream<T> dùng Comparator. Primitive streams có sẵn min/max:

~~~java
OptionalInt min = IntStream.of(7, 3, 10).min();
OptionalInt max = IntStream.of(7, 3, 10).max();
~~~

Kết quả lần lượt chứa 3 và 10. Đây là **OptionalInt**, không phải Optional<Integer>.

Tương tự:

~~~java
OptionalLong largest = LongStream.of(4L, 8L).max();
OptionalDouble smallest = DoubleStream.of(2.5, 1.5).min();
~~~

Đặc điểm:

- Không cần Comparator ở primitive stream.
- Không cần boxing giá trị int/long/double cho phép reduction cốt lõi.
- Với nguồn rỗng, trả OptionalInt/OptionalLong/OptionalDouble rỗng.
- Muốn chọn object theo một thuộc tính int và vẫn giữ **cả object**, dùng Stream<Product>.min(Comparator.comparingInt(Product::price)).
- Muốn chỉ nhận con số tối thiểu của thuộc tính, dùng products.stream().mapToInt(Product::price).min().

Ví dụ:

~~~java
int minPrice = products.stream()
    .mapToInt(Product::price)
    .min()
    .orElseThrow();
~~~

Kết quả là giá, không phải Product. Đây là lựa chọn hợp lý khi mục đích là thống kê một thuộc tính, tránh tạo/cất giữ wrapper không cần thiết.

### 8.1. Số thực có NaN và signed zero

DoubleStream.min/max có ngữ nghĩa với **NaN** và **-0.0/+0.0** cần chú ý. Trong Java, Double.compare và phép so sánh số học thông thường không hoàn toàn đồng nhất ở những trường hợp này. Theo hợp đồng DoubleStream.min/max, nếu có NaN thì kết quả là NaN; với zero, min coi -0.0 nhỏ hơn +0.0 và max coi +0.0 lớn hơn -0.0.

Nếu dữ liệu nghiệp vụ không cho phép NaN hoặc Infinity, nên validate trước thay vì mong min/max tự xử lý theo ý nghĩa nghiệp vụ.

Ví dụ:

~~~java
double min = DoubleStream.of(4.0, Double.NaN, 1.0)
    .min()
    .orElseThrow();
// Kết quả là NaN.
~~~

Khi tính tiền, tránh dùng double tùy tiện nếu cần chính xác chữ số thập phân; cân nhắc BigDecimal và comparator thích hợp theo chính sách tiền tệ.

## 9. Optional và null trong min/max

Không nên đưa phần tử null vào Stream rồi mong Optional chứa null:

~~~java
List<String> values = new ArrayList<>();
values.add(null);
values.add("Java");
~~~

Nếu min/max reduction chọn null, việc tạo Optional kết quả có thể ném NullPointerException. Dùng comparator nullsFirst/nullsLast **không đảm bảo** min/max có thể trả null trong Optional.

Cách xử lý thường rõ ràng nhất:

~~~java
Optional<String> result = values.stream()
    .filter(Objects::nonNull)
    .min(Comparator.naturalOrder());
~~~

Nếu yêu cầu nghiệp vụ coi null là “không có giá trị”, lọc null trước khi chọn cực trị là hợp lý. Nếu null là một trạng thái đặc biệt cần thể hiện trong kết quả, hãy thiết kế kiểu bao bọc/đánh dấu trạng thái một cách tường minh, thay vì để Optional<T> mang null.

### 9.1. Khóa so sánh có thể null khác phần tử null

~~~java
Comparator<Product> byNullableSku =
    Comparator.comparing(
        Product::sku,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Điều này phù hợp khi Product không null nhưng Product.sku() có thể null. Nếu chính Product là null, Product::sku không có receiver hợp lệ.

Có thể dùng Comparator.nullsFirst/last ở **cấp Product** với comparator con, nhưng kết quả min/max vẫn bị ràng buộc bởi khả năng Optional không giữ null. Trong nhiều bài toán, loại bỏ null ở nguồn là phương án dễ hiểu hơn.

## 10. Chọn phần tử cực trị trong dữ liệu có trùng giá trị

Giả sử hai sản phẩm có giá 450. Nếu comparator chỉ so sánh price, cả hai đều là **ứng viên tối đa**.

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

Với một phần tử hòa, kết quả hợp lệ có thể là bất kỳ object nào cùng cực trị theo comparator. **Không nên dựa vào quy tắc chọn “phần tử nào xuất hiện trước” làm hợp đồng nghiệp vụ của min/max**, nhất là khi chuyển sang parallel stream.

Nếu bài toán yêu cầu **tất cả** sản phẩm cùng giá cao nhất, min/max chỉ trả một đối tượng sẽ không đủ. Có thể thực hiện hai bước trên một Collection ổn định:

~~~java
int maximum = products.stream()
    .mapToInt(Product::price)
    .max().orElseThrow();

List<Product> allMostExpensive = products.stream()
    .filter(product -> product.price() == maximum)
    .toList();
~~~

Đoạn này tạo **hai stream mới** từ Collection products; không tái sử dụng một Stream đã tiêu thụ. Nó chỉ đúng khi nguồn phù hợp để duyệt lại, dữ liệu không bị thay đổi giữa hai lượt và price có ý nghĩa theo quy tắc đang xét.

Nếu chỉ cần **một** đại diện ổn định theo thứ tự hoàn toàn xác định, thêm thenComparing theo mã duy nhất là đơn giản hơn:

~~~java
Comparator<Product> byPriceThenSku =
    Comparator.comparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

Nếu còn nhiều phần tử hòa cả price và sku, cần xác định thêm một khóa duy nhất hoặc chính sách tie-break khác.

### 10.1. So sánh với reduce

Có thể mô tả min bằng phép reduction:

~~~java
Optional<Product> cheapest = products.stream()
    .reduce((left, right) ->
        byPrice.compare(left, right) <= 0 ? left : right);
~~~

Nhưng cách này dài và dễ sai khi đổi quy tắc so sánh, xử lý null hoặc parallel. Khi đã có Comparator, **Stream.min(byPrice)** diễn đạt ý định trực tiếp và dễ review hơn.

## 11. Comparator trong Stream.max/min khác Comparator trong sorted thế nào?

**Comparator không thay đổi bản chất** khi dùng ở các API khác. Điều thay đổi là mục tiêu của phép toán:

~~~java
products.stream().min(byPrice);        // Chọn một phần tử đứng đầu
products.stream().max(byPrice);        // Chọn một phần tử đứng cuối
products.stream().sorted(byPrice);     // Tạo pipeline có thứ tự
~~~

Các comparator dùng chung được tái sử dụng ở nhiều nơi; điều quan trọng là khai báo chúng có **nghĩa nghiệp vụ rõ ràng**. Khi duyệt API hoặc đọc code, cần phân biệt:

- **Thứ tự tự nhiên/giá trị so sánh:** quy tắc Comparator.
- **Cực trị nào cần tìm:** min hay max.
- **Nguồn ứng viên:** những phần tử còn lại sau filter.
- **Hòa thứ hạng:** có tiêu chí phụ hay cần trả tất cả ứng viên hòa.
- **Kết quả cần gì:** một Product hay chỉ số price.

Không dùng cùng một comparator vừa so sánh theo price vừa mong nó chọn theo score; cần một comparator khác cho score.

## 12. Chương trình Java 17+ chạy hoàn chỉnh

Chương trình sử dụng record Product với ba trường sku, price, score; các comparator cho giá, điểm và tie-break. Nó minh họa trực tiếp:

- min theo giá rồi mã sản phẩm.
- max theo giá rồi mã sản phẩm khi nhiều sản phẩm cùng giá cao nhất.
- max theo score rồi mã sản phẩm.
- max trên comparator reversed.
- Stream rỗng và Optional.empty.
- Natural order với Integer.
- IntStream min trên thuộc tính price.
- Danh sách đầu vào không thay đổi.

Tạo tệp **StreamMinMaxDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class StreamMinMaxDemo {
    record Product(String sku, int price, int score) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("Book", 120, 4),
            new Product("Pen", 20, 4),
            new Product("Lamp", 450, 5),
            new Product("Case", 120, 3),
            new Product("Glass", 450, 5)
        );

        Comparator<Product> byPriceThenSku =
            Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);

        Product cheapest = products.stream()
            .min(byPriceThenSku).orElseThrow();
        Product mostExpensive = products.stream()
            .max(byPriceThenSku).orElseThrow();
        System.out.println("min-price=" + cheapest.sku() + ":" + cheapest.price());
        System.out.println("max-price=" + mostExpensive.sku() + ":" + mostExpensive.price());

        Comparator<Product> byScoreThenSku =
            Comparator.comparingInt(Product::score)
                .thenComparing(Product::sku);
        System.out.println("max-score=" + products.stream()
            .max(byScoreThenSku).orElseThrow().sku());

        System.out.println("max-reversed=" + products.stream()
            .max(byPriceThenSku.reversed()).orElseThrow().sku());

        Optional<Product> missing = Stream.<Product>empty()
            .min(byPriceThenSku);
        System.out.println("empty=" + missing.isEmpty());

        System.out.println("natural=" + Stream.of(7, 3, 10, 4)
            .min(Comparator.naturalOrder()).orElseThrow());

        System.out.println("min-int=" + products.stream()
            .mapToInt(Product::price).min().orElseThrow());

        System.out.println("original-size=" + products.size());
    }
}
~~~

Trong thư mục chứa tệp, chạy bằng JDK 17 trở lên:

~~~bash
javac StreamMinMaxDemo.java
java StreamMinMaxDemo
~~~

**Stdout chính xác:**

~~~text
min-price=Pen:20
max-price=Lamp:450
max-score=Lamp
max-reversed=Pen
empty=true
natural=3
min-int=20
original-size=5
~~~

### 12.1. Vì sao kết quả như vậy?

**min-price:** Pen có giá 20, là nhỏ nhất trong danh sách.

**max-price:** Lamp và Glass cùng giá 450, nên so theo SKU; "Lamp" đứng sau "Glass" trong thứ tự tự nhiên, vì vậy max(byPriceThenSku) chọn Lamp.

**max-score:** Lamp và Glass cùng score 5; tiêu chí SKU lại làm Lamp đứng sau Glass, nên được chọn.

**max-reversed:** byPriceThenSku.reversed() đảo toàn bộ thứ tự, khiến phần tử đứng cuối theo comparator đảo là phần tử đứng đầu theo comparator gốc: Pen.

**empty:** Stream.<Product>empty().min(...) không tìm thấy sản phẩm, trả Optional.empty. isEmpty() là true.

**natural:** số tự nhiên nhỏ nhất trong 7, 3, 10, 4 là 3.

**min-int:** mapToInt tạo IntStream giá của sản phẩm; min() không cần Comparator và trả OptionalInt có giá trị 20.

**original-size:** thao tác min/max không sửa danh sách products, nên kích thước vẫn 5.

Chương trình dùng record không có trường null, giá và score cố định, nên kết quả comparator ổn định. Nó không tự kiểm tra tất cả invariant nghiệp vụ (như giá không âm); ứng dụng thực cần validation phù hợp.

## 13. Các trường hợp cần lưu ý trong sản phẩm thật

### 13.1. Comparator có thể không tương thích equals

Nếu Product.equals so sánh tất cả các component, nhưng comparator chỉ so sánh price, hai Product khác nhau có thể cho compare(a,b) == 0. Điều đó **không ngăn min/max tìm cực trị**, nhưng khiến việc xác định một Product duy nhất khi hòa trở nên cần thiết.

Với TreeSet hoặc TreeMap, comparator còn ảnh hưởng nhận dạng khóa/phần tử theo thứ tự và có thể làm hai object khác nhau bị xem như một entry. Đây là bối cảnh bổ sung nhắc bạn không đánh đồng comparator zero với equals.

### 13.2. Comparator chứa trạng thái mutable

Không nên dùng comparator đọc số điểm đang thay đổi trong quá trình pipeline, hoặc so sánh theo đồng hồ ngẫu nhiên. Điều đó có thể vi phạm tính bắc cầu hoặc nhất quán, và khiến kết quả min/max không đáng tin.

### 13.3. Xử lý stream song song

Stream.min/max có thể chạy trên parallel stream với phép reduction phù hợp, nhưng comparator phải tuân thủ hợp đồng và **không có tác dụng phụ gây tranh chấp**. Không sửa List nguồn từ callback hay comparator.

Đừng dựa vào số lần compare() chính xác để cập nhật bộ đếm hay ghi dữ liệu nghiệp vụ; số lần và thứ tự so sánh không phải hợp đồng công khai của Stream.min/max.

### 13.4. Không nên dùng comparator để sửa đối tượng

Sai ý định:

~~~java
Comparator<Product> strange = (left, right) -> {
    updateAudit(left);   // Side effect giả định
    return Integer.compare(left.price(), right.price());
};
~~~

Đây là mã minh họa, updateAudit không phải Java API có sẵn. Comparator nên **chỉ so sánh**. Nếu ghi audit là bắt buộc, đặt ở bước điều phối riêng với cơ chế một lần/transaction/retry rõ ràng; không sử dụng số lần comparator được gọi để quyết định side effect.

### 13.5. Dữ liệu lớn và phép toán stateful

Nếu cần chỉ một cực trị, min/max thường ít tốn tài nguyên hơn sorted().findFirst(). Nhưng nếu nguồn đã được indexed hoặc có index trong database, truy vấn bên nguồn như SQL ORDER BY ... LIMIT 1 hoặc MIN/MAX có thể hiệu quả hơn tải toàn bộ bản ghi vào Java. Cần dựa vào ràng buộc nghiệp vụ, DB index và profiling, không mặc định Stream luôn tối ưu.

### 13.6. String và locale

Comparator.naturalOrder() cho String không thay thế quy tắc sắp xếp phù hợp tiếng Việt hoặc ngôn ngữ khác. Khi cần so sánh người dùng nhìn thấy theo locale, cân nhắc **Collator** với chính sách locale rõ ràng, đồng thời đảm bảo comparator ổn định và phù hợp đồng thời nếu dùng chung.

### 13.7. Số tiền và độ chính xác

Nếu price là BigDecimal:

~~~java
Comparator<Product> byAmount =
    Comparator.comparing(Product::amount);
~~~

Đoạn minh họa này giả định Product.amount() trả BigDecimal và không null. BigDecimal.compareTo so sánh giá trị số (ví dụ 2.0 so với 2.00 có thể cho kết quả 0), trong khi BigDecimal.equals còn xét scale. Do đó comparator bằng 0 không bắt buộc có cùng nghĩa với equals; bổ sung tie-break nếu cần.

## 14. Lỗi phổ biến

**Lỗi 1 — gọi min() hoặc max() không có comparator trên Stream<T>.** Với object Stream<T>, phải cung cấp Comparator<? super T>. Phương thức min/max không tham số chỉ có trên primitive streams như IntStream.

**Lỗi 2 — quên Optional.** min/max trên Stream<T> trả Optional<T>, không trả trực tiếp T. get() trên Optional.empty ném NoSuchElementException.

**Lỗi 3 — đảo comparator rồi vẫn nghĩ max là số lớn nhất.** max(reverseOrder()) thường chọn số nhỏ nhất theo natural order. Hãy diễn giải “cuối theo comparator” thay vì dựa vào tên method.

**Lỗi 4 — comparator trả left.price() - right.price().** Phép trừ int có thể overflow. Dùng Integer.compare hoặc Comparator.comparingInt.

**Lỗi 5 — không xử lý trường hợp hòa.** Khi nhiều sản phẩm có cùng giá, comparator theo giá không xác định duy nhất sản phẩm nào được chọn. Dùng thenComparing hoặc trả tất cả phần tử cùng cực trị nếu nghiệp vụ yêu cầu.

**Lỗi 6 — dùng sorted chỉ để lấy min.** Việc sắp tất cả thường không cần thiết khi mục tiêu chỉ là chọn một cực trị.

**Lỗi 7 — dùng comparator theo một field nhưng mong chọn theo field khác.** Comparator.comparingInt(Product::price) chọn theo giá; muốn chọn score cần comparator khác.

**Lỗi 8 — cho phép null mà chưa thiết kế.** Optional không chứa null; min/max với kết quả null có thể ném NullPointerException. Lọc null hoặc biểu diễn trạng thái thiếu bằng kiểu rõ nghĩa.

**Lỗi 9 — tưởng Stream.min/max tự chỉnh sửa nguồn.** Chúng chọn kết quả từ stream, không xóa hoặc sắp lại Collection nguồn. Callback can thiệp nguồn vẫn có thể gây lỗi.

**Lỗi 10 — dùng Comparator.naturalOrder cho mọi kiểu.** Kiểu không Comparable thích hợp sẽ không thỏa ràng buộc generic; hãy định nghĩa comparator dựa trên thuộc tính hoặc quy tắc nghiệp vụ.

**Lỗi 11 — nhầm natural order của String với locale order.** So sánh String mặc định không tương đương sắp từ tiếng Việt theo quy tắc ngôn ngữ.

**Lỗi 12 — dùng mapToInt để lấy cực trị rồi mong lấy object.** IntStream.min trả số int; muốn cả Product phải giữ Stream<Product> và so sánh theo thuộc tính.

**Lỗi 13 — tái sử dụng cùng Stream để tìm min rồi max.** Một Stream instance không được tiêu thụ hai lần. Gọi products.stream() hai lần nếu nguồn có thể duyệt lại, hoặc tính cả hai cực trị bằng một collector/custom reduction khi cần hiệu quả.

**Lỗi 14 — comparator phụ thuộc state hoặc side effect.** Kết quả min/max trở nên thiếu tin cậy, đặc biệt trên parallel stream; không dùng comparator để ghi audit.

**Lỗi 15 — quên chi phí dữ liệu nguồn.** Với nguồn I/O-backed hoặc database, có thể cần close hoặc truy vấn server-side để tránh tải hết dữ liệu chỉ nhằm tìm min/max.

## 15. Checklist khi chọn phương pháp

| Mục tiêu | Cách thường hợp lý |
| --- | --- |
| Tìm Product rẻ nhất | products.stream().min(Comparator.comparingInt(Product::price)) |
| Tìm Product đắt nhất | products.stream().max(Comparator.comparingInt(Product::price)) |
| Tìm một Product theo hai tiêu chí | comparingInt(...).thenComparing(...) |
| Tìm giá int nhỏ nhất | products.stream().mapToInt(Product::price).min() |
| Tìm min trên Integer | Stream<Integer>.min(Comparator.naturalOrder()) |
| Muốn kết quả khi rỗng | Optional.orElse/orElseGet hoặc return Optional |
| Rỗng là lỗi | Optional.orElseThrow |
| Muốn tất cả phần tử cùng cực trị | Tìm giá trị cực trị rồi lọc lại nguồn ổn định |
| Muốn top N theo nhiều tiêu chí | Sắp xếp + limit hoặc thuật toán top-k phù hợp |
| Muốn thứ tự toàn bộ danh sách | sorted(comparator).toList() |
| Có String key nullable | Comparator.nullsFirst/nullsLast ở cấp key, kiểm tra null element riêng |
| Dữ liệu là tiền tệ | Kiểu số và comparator phù hợp quy tắc độ chính xác |

## 16. Câu hỏi tự kiểm tra

1. Vì sao Stream<Product>.min yêu cầu Comparator, còn IntStream.min không cần?
2. Khi truyền Comparator.reverseOrder vào max, kết quả có ý nghĩa gì so với natural order?
3. Optional.empty xuất hiện khi nào và vì sao không nên gọi get trực tiếp?
4. Với hai Product có giá bằng nhau, compare(a,b) == 0 có bảo đảm a.equals(b) không?
5. thenComparing giúp thay đổi cách chọn phần tử hòa thế nào?
6. Vì sao Comparator.comparingInt tốt hơn phép trừ hai int để so sánh?
7. Nếu cần tất cả sản phẩm giá cao nhất, min/max trả một object có đủ không?
8. Vì sao sorted().findFirst() có thể tốn hơn min() khi chỉ cần một cực trị?
9. Khác biệt giữa Product min theo price và giá trị int min từ mapToInt là gì?
10. Nếu có phần tử null, Comparator.nullsFirst đã bảo đảm Optional trả null được chưa?
11. Tại sao biến Comparator theo field mutable trong lúc xử lý là nguy hiểm?
12. Vì sao natural order của String không phải chuẩn sắp xếp theo locale tiếng Việt?
13. Trong Stream song song, có nên cập nhật một biến đếm trong Comparator.compare không?
14. Làm thế nào tái sử dụng Collection để lấy cả min và max mà không tái sử dụng cùng Stream?
15. Khi có database và chỉ cần sản phẩm rẻ nhất, vì sao truy vấn có index đôi khi phù hợp hơn xử lý tất cả object ở Java?

**Kết luận:** **min và max chọn cực trị theo thứ tự Comparator**, không theo một nghĩa cố định của “nhỏ” hoặc “lớn”. Với object Stream, kết quả luôn là Optional<T>; cần xử lý rỗng, null, kiểu dữ liệu và chính sách hòa. Khi chỉ cần một phần tử, dùng min/max trực tiếp với Comparator có tên và tie-break rõ ràng; dùng primitive stream khi chỉ cần giá trị số; dùng sorted khi thật sự cần thứ tự toàn bộ.