# Mô hình hóa quan hệ kiểu thay cho ép kiểu tại nơi sử dụng

## 1. Mục tiêu: API giữ điều gì mà nơi gọi đang phải đoán?

Một API trả về `Object` thường buộc nơi gọi phải biết thêm một quy ước ngoài chữ ký:

```java
Object value = cache.get("P-01");
Product product = (Product) value;
```

Đây là đoạn minh họa, giả sử `cache.get` có kiểu trả về `Object` và `Product` là một lớp nghiệp vụ.

Phép cast khẳng định rằng giá trị lúc chạy phù hợp với `Product`; nó không chứng minh nơi ghi dữ liệu đã luôn tuân thủ quy ước. Nếu API cho phép gắn một chuỗi vào cùng khóa, lỗi chỉ xuất hiện khi nơi gọi chuyển kiểu.

Một thiết kế tổng quát có thể đưa quy ước đó vào hợp đồng:

```java
Store<String, Product> products = new Store<>();
products.put("P-01", new Product("P-01", 7));

Optional<Product> result = products.find("P-01");
```

Giờ quan hệ được mô tả bằng kiểu:

```text
Store<K, V>
    put nhận K và V
    find nhận K
    find trả Optional<V>
```

Với một kho cụ thể, `K = String` và `V = Product`. Nơi gọi không cần tự cast từ `Object`.

Đích của thiết kế API tổng quát không phải thêm thật nhiều dấu `<...>`. Đó là **đặt tên và giữ các quan hệ kiểu mà thuật toán thực sự có thể bảo đảm**. Các cơ chế này vẫn áp dụng trên Java hiện đại; ví dụ hoàn chỉnh dùng Java 17+.

## 2. Một tham số kiểu cần đại diện cho một quan hệ có thật

Xét một hộp có trạng thái:

```java
class Box<T> {
    private T value;

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Ở đây `T` nối ba vị trí:

- Kiểu dữ liệu được lưu trong trường.
- Kiểu giá trị được truyền vào `set`.
- Kiểu kết quả được lấy ra bằng `get`.

Với `Box<Product>`, trình biên dịch kiểm tra việc ghi và cho nơi đọc nhận `Product`. Cast ở nơi sử dụng biến mất vì quan hệ đã được bảo vệ ở nơi xây dựng và cập nhật trạng thái.

Không nên hiểu `T` là “bất kỳ kiểu nào ở bất kỳ thời điểm nào”. Với một `Box<Product>`, kiểu phần tử đã được cố định trong hợp đồng của tham chiếu đó. Muốn một hộp nhận nhiều loại dữ liệu không liên hệ, đó là một thiết kế khác cần mô hình hóa riêng.

### 2.1. Tham số kiểu của lớp và của phương thức

Dùng tham số kiểu trên lớp khi nhiều thao tác của cùng đối tượng cần chia sẻ quan hệ kiểu:

```java
class Store<K, V> {
    // Các thao tác của một kho cùng dùng K và V.
}
```

Dùng tham số kiểu trên phương thức khi quan hệ chỉ tồn tại trong một lần gọi:

```java
static <S, T> List<T> mapAll(
        List<? extends S> source,
        Function<? super S, ? extends T> mapper) {
    List<T> result = new ArrayList<>();
    for (S value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Các đoạn này cần import kiểu tương ứng từ `java.util` và `java.util.function`.

`S` nối dữ liệu nguồn với đầu vào của phép biến đổi; `T` nối đầu ra của phép biến đổi với phần tử danh sách kết quả. Mỗi lần gọi có thể sử dụng một cặp kiểu khác nhau, không cần một đối tượng `Mapper<S, T>` có trạng thái nếu thuật toán không yêu cầu.

## 3. Khi có nhiều vai trò, dùng nhiều tham số kiểu

Một API kiểu:

```java
interface Repository<T> {
    T find(T id);
}
```

đang hứa rằng mã định danh và thực thể có cùng một kiểu. Điều này thường sai với một kho sản phẩm có mã `String` và thực thể `Product`.

Mô hình phù hợp hơn có hai vai trò riêng:

```java
interface Repository<ID, E> {
    Optional<E> find(ID id);
    void save(ID id, E entity);
}
```

`ID` và `E` không cần có quan hệ kế thừa. Chúng cần được dùng nhất quán theo hai vai trò khác nhau.

Với khai báo:

```java
Repository<String, Product> products;
```

chữ ký tương ứng là `find(String)` trả `Optional<Product>`, còn `save` nhận mã chuỗi và thực thể sản phẩm.

### 3.1. Kiểu bảo đảm đến đâu?

Thiết kế trên chặn sai kiểu như truyền một số nguyên làm mã khi API yêu cầu `String`. Nó chưa tự bảo đảm rằng chuỗi là mã sản phẩm hợp lệ hoặc mã trong đối tượng bằng mã ở đối số.

Nếu những quan hệ nghiệp vụ đó quan trọng, có thể dùng kiểu định danh riêng, kiểm tra trong thao tác lưu hoặc chọn API lấy mã trực tiếp từ thực thể. Không nên tuyên bố rằng generics tự xác thực mọi dữ liệu.

Ví dụ, hai mã đều dùng `String` như mã người dùng và mã đơn hàng vẫn có thể bị dùng nhầm. Một kiểu `ProductId` hoặc `OrderId` riêng có thể diễn đạt sự khác nhau đó rõ hơn.

## 4. Dùng wildcard để mở phạm vi mà vẫn giữ quan hệ

Chữ ký `mapAll` ở mục 2 không bắt mọi đối số kiểu phải trùng khít:

```java
<S, T> List<T> mapAll(
        List<? extends S> source,
        Function<? super S, ? extends T> mapper)
```

Cách đọc:

1. Nguồn cung cấp các giá trị dùng được như `S`.
2. Hàm xử lý nhận được `S`, nên có thể nhận cả một kiểu cha của `S`.
3. Hàm xử lý cung cấp kết quả dùng được như `T`.
4. Phương thức gom các kết quả đó thành `List<T>`.

Wildcard điều chỉnh phạm vi từng vị trí; các tên `S` và `T` vẫn giữ liên hệ giữa các vị trí.

Nếu thay mọi thứ bằng `List<?>`, `Function<?, ?>` và `List<?>`, ta đã che các kiểu mà chưa biểu đạt được cách nối đầu ra nguồn với đầu vào hàm. Hai dấu hỏi độc lập không bảo đảm cùng một kiểu.

Ở chiều ngược lại, không nên trả `Object` chỉ để chấp nhận nhiều loại kết quả. `List<T>` giữ quan hệ với kết quả của `mapper` mà vẫn tổng quát.

## 5. “Thêm <T> vào hàm trả Object” chưa tạo hợp đồng an toàn

Một API đọc dữ liệu tùy ý theo khóa chuỗi không thể bảo đảm một kiểu kết quả bất kỳ chỉ bằng chữ ký:

```java
// Chữ ký đáng nghi nếu bên trong chỉ đọc một Object theo chuỗi:
<T> T read(String key)
```

Nếu một nơi viết:

```java
Product product = read("same-key");
```

còn nơi khác viết:

```java
String text = read("same-key");
```

thì `T` có thể được suy luận từ kiểu đích khác nhau. Chữ ký không cung cấp bằng chứng rằng giá trị được lưu phù hợp với cả hai yêu cầu.

Nếu phần cài đặt chỉ dùng `(T) value` và thêm `@SuppressWarnings("unchecked")`, cast đã được giấu vào thư viện; quan hệ kiểu chưa được bảo vệ.

Điểm cần kiểm tra là: **T được bảo đảm từ nguồn nào?**

- Trạng thái của đối tượng đã mang `T`, như `Box<T>`?
- Một tham số đầu vào giữ quan hệ, như `List<T>`?
- Một hàm được truyền vào cung cấp `T`, như `Supplier<? extends T>`?
- Một bộ giải mã hoặc đối tượng mô tả kiểu có hợp đồng trả `T`?

Không phải mọi kiểu `T` chỉ xuất hiện ở đầu ra đều sai. Chẳng hạn, một phương thức tạo danh sách rỗng `<T> List<T> empty()` không cần lấy phần tử tùy ý rồi khẳng định nó có kiểu `T`. Hãy đánh giá theo cách phương thức tạo hoặc thu nhận giá trị, không dùng một quy tắc đếm số lần xuất hiện của tên kiểu.

## 6. Chương trình hoàn chỉnh: kho có kiểu và phép biến đổi có quan hệ

Lưu thành `TypedApiDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

public class TypedApiDemo {
    record Product(String sku, int stock) {
        Product {
            Objects.requireNonNull(sku, "sku");
            if (stock < 0) {
                throw new IllegalArgumentException("stock must be non-negative");
            }
        }
    }

    static final class Store<K, V> {
        private final Map<K, V> values = new HashMap<>();

        void put(K key, V value) {
            values.put(
                    Objects.requireNonNull(key, "key"),
                    Objects.requireNonNull(value, "value"));
        }

        Optional<V> find(K key) {
            Objects.requireNonNull(key, "key");
            return Optional.ofNullable(values.get(key));
        }
    }

    static <S, T> List<T> mapAll(
            List<? extends S> source,
            Function<? super S, ? extends T> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(mapper, "mapper");

        List<T> result = new ArrayList<>();
        for (S value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    public static void main(String[] args) {
        Store<String, Product> products = new Store<>();
        Product keyboard = new Product("P-01", 7);
        Product mouse = new Product("P-02", 12);

        products.put(keyboard.sku(), keyboard);
        products.put(mouse.sku(), mouse);

        Product found = products.find("P-01").orElseThrow();
        List<Product> selected = List.of(found, mouse);
        List<String> skus = mapAll(selected, Product::sku);
        List<Integer> stocks = mapAll(selected, Product::stock);

        System.out.println("found = " + found.sku());
        System.out.println("stock = " + found.stock());
        System.out.println("skus = " + skus);
        System.out.println("stocks = " + stocks);
        System.out.println("missing = " + products.find("P-99").isEmpty());

        // Các dòng sau cố ý để comment vì không biên dịch:
        // products.put("P-03", "not a product");
        // products.find(123);
        // String wrong = products.find("P-01").orElseThrow();
    }
}
```

Biên dịch và chạy với JDK 17+:

```shell
javac --release 17 -Xlint:all TypedApiDemo.java
java TypedApiDemo
```

Stdout chính xác:

```text
found = P-01
stock = 7
skus = [P-01, P-02]
stocks = [7, 12]
missing = true
```

Những quan hệ được chương trình bảo vệ:

| Quan hệ | Nơi mô hình hóa |
| --- | --- |
| Khóa lưu và khóa tìm có cùng kiểu `K` | `Store<K, V>`, `put(K, V)`, `find(K)` |
| Giá trị lưu và kết quả đọc cùng kiểu `V` | `Map<K, V>`, `Optional<V>` |
| Phần tử nguồn phù hợp với đầu vào hàm | `S`, `? extends S`, `? super S` |
| Kết quả hàm phù hợp với phần tử danh sách trả về | `T`, `? extends T`, `List<T>` |

Không có cast ở nơi sử dụng và cũng không có cast không được kiểm tra trong phần cài đặt này. `Optional` mô tả việc có thể không tìm thấy; nó không thay thế tham số kiểu `V`, mà bổ sung hợp đồng vắng mặt cho kết quả.

`Store` không nhận khóa hoặc giá trị `null`; quyết định đó giúp `Optional.empty()` biểu thị việc không có ánh xạ. `mapAll` trong ví dụ vẫn cho phép hàm trả `null`; nếu ứng dụng cấm kết quả đó, cần nêu rõ và kiểm tra riêng. Generics không tự cung cấp chính sách `null`.

## 7. Khi ranh giới dữ liệu thật sự là động

Một tập hợp chứa nhiều loại giá trị dưới các khóa khác nhau có thể cần một mô hình khác với `Store<K, V>` đồng nhất.

Ví dụ một kho dịch vụ tra theo lớp:

```java
final class Services {
    private final Map<Class<?>, Object> values = new HashMap<>();

    <T> void register(Class<T> type, T value) {
        Objects.requireNonNull(type, "type");
        Objects.requireNonNull(value, "value");
        values.put(type, type.cast(value));
    }

    <T> Optional<T> find(Class<T> type) {
        Objects.requireNonNull(type, "type");
        Object value = values.get(type);
        return Optional.ofNullable(type.cast(value));
    }
}
```

Đây là đoạn lớp minh họa, cần các import `Map`, `HashMap`, `Objects`, `Optional` như ví dụ chính.

Nơi gọi:

```java
Services services = new Services();
services.register(String.class, "configured");

String value = services.find(String.class).orElseThrow();
```

`Class<T>` nối khóa tra cứu với kiểu kết quả. `Class.cast` thực hiện kiểm tra lúc chạy dựa trên lớp thật, thay vì một cast sang biến kiểu không được kiểm tra.

Map bên trong không tự diễn đạt đầy đủ quan hệ “khóa lớp nào thì giá trị thuộc lớp đó” bằng `Map<Class<?>, Object>`. Phần cài đặt phải bảo vệ bất biến này: giữ map private, kiểm soát mọi đường ghi và kiểm tra tại ranh giới. Nơi gọi nhận lại một hợp đồng rõ ràng.

Giới hạn của mẫu này:

- Mỗi khóa lớp lưu một giá trị; muốn nhiều dịch vụ cùng lớp cần thiết kế khóa khác.
- `Class<T>` đơn giản không phân biệt `List<String>` với `List<Integer>`.
- Mẫu không biến mọi dữ liệu động thành an toàn tĩnh hoàn toàn; nó tập trung kiểm tra runtime vào ranh giới đã xác định.

Với dữ liệu từ JSON, cơ sở dữ liệu hoặc mạng, cũng cần một bước giải mã/xác thực có hợp đồng rõ ràng. `<T>` không tự kiểm tra cấu trúc dữ liệu ngoài chương trình.

## 8. Cách refactor một API có nhiều cast

### Bước 1: tìm quy ước đang bị lặp ở nơi gọi

Ví dụ: mọi kết quả của một kho đều bị cast sang `Product`; hoặc kiểu kết quả của một phép chuyển đổi luôn phụ thuộc vào hàm được truyền vào.

Nếu những cast đó diễn đạt cùng một quan hệ ổn định, quan hệ có thể thuộc về chữ ký API.

### Bước 2: đặt tên cho các vai trò độc lập

Một kiểu phần tử dùng `T`; khóa và giá trị có thể dùng `K, V`; đầu vào và đầu ra phép biến đổi có thể dùng `S, T`.

Không dùng cùng một tên kiểu cho hai vai trò không bắt buộc giống nhau. Cũng không thêm nhiều tên khác nhau khi thuật toán thực sự đòi cùng một kiểu.

### Bước 3: bảo vệ từ nơi tạo và ghi dữ liệu

Một hàm đọc trả `V` chỉ đáng tin khi dữ liệu được tạo hoặc ghi theo hợp đồng tương ứng. Giữ cấu trúc nội bộ đúng kiểu và tránh để một đường ghi `Object` phá vỡ quy ước.

### Bước 4: nới phạm vi bằng wildcard ở nơi cần

Nếu một tham số chỉ cung cấp giá trị, cân nhắc `extends`; nếu nó nhận giá trị, cân nhắc `super`. Giữ kiểu trả về thuận tiện khi phần cài đặt có thể bảo đảm kiểu đó.

### Bước 5: kiểm tra cả cách dùng đúng lẫn cách dùng sai

Một thiết kế tốt cần cho phép trường hợp hợp lệ mà không cast và chặn trường hợp sai ngay khi biên dịch. Ví dụ chính có cả hai loại: chương trình chạy thành công và ba dòng sai kiểu được đánh dấu rõ.

Nếu phải thêm cast không được kiểm tra chỉ để phần cài đặt “qua được compiler”, hãy kiểm tra xem chữ ký có đang hứa điều mà dữ liệu nội bộ không bảo đảm hay không.

## 9. Giữ đúng giới hạn của hợp đồng kiểu

Generics kiểm tra quan hệ kiểu trong mã nguồn; xóa kiểu không làm các quan hệ đó vô ích. Trình biên dịch vẫn kiểm tra lời gọi và có thể sinh cast trong bytecode tại vị trí cần thiết.

Điều API loại bỏ là các khẳng định kiểu thủ công, lặp lại và dễ sai ở nơi sử dụng. Nó không có nghĩa:

- Mọi cast đều biến mất khỏi bytecode.
- Dữ liệu đã đúng quy tắc nghiệp vụ.
- Đối tượng trở thành bất biến hoặc an toàn cho nhiều luồng.
- `null` hay dữ liệu bên ngoài đã được xác thực.

Một chữ ký nên được đọc thành một lời hứa cụ thể: “giá trị đọc ra có kiểu tương ứng với giá trị được phép ghi vào”, hoặc “kết quả có kiểu mà bộ chuyển đổi cung cấp”. Nếu không đọc được lời hứa đó từ các quan hệ đầu vào, trạng thái và đầu ra, việc thêm tham số kiểu có thể chỉ đang che một cast.

## Tài liệu đối chiếu

- [Oracle — Generic Types](https://docs.oracle.com/javase/tutorial/java/generics/types.html): dùng tham số kiểu để giữ quan hệ giữa dữ liệu lưu, đầu vào và đầu ra.
- [Oracle — Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html): phạm vi tham số kiểu của một phương thức.
- [Java Function API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html): quan hệ kiểu đầu vào–đầu ra của hàm chuyển đổi.
- [Java Class.cast API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): kiểm tra chuyển kiểu bằng thông tin lớp lúc chạy.
