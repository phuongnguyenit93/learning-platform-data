# Xây dựng API generic với giới hạn kiểu và wildcard

## 1. Bài toán thực hành: một kho dữ liệu dùng lại được

Cần xây dựng một API kho dữ liệu trong bộ nhớ cho nhiều kiểu đối tượng có mã định danh. Ví dụ, một danh mục sản phẩm có thể nhận cả sản phẩm thông thường và sách, nhưng một danh mục chỉ dành cho sách không được nhận sản phẩm bất kỳ.

Yêu cầu:

1. Kiểu đối tượng phải cung cấp mã định danh đúng kiểu mà kho sử dụng.
2. Nhập được một nhóm đối tượng thuộc kiểu con.
3. Xuất được dữ liệu sang một tập hợp chứa kiểu cha.
4. Chuyển đổi phần tử bằng một hàm có đầu vào/đầu ra tương thích.
5. Phát hiện việc kết hợp kiểu sai ngay khi biên dịch.
6. Không dùng kiểu thô hoặc ép kiểu không được kiểm chứng để né trình biên dịch.

Ở đây, “API” là giao diện lập trình Java gồm lớp và phương thức; không cần tạo HTTP endpoint.

Generics giúp mô tả **quan hệ giữa các kiểu**. Giới hạn kiểu quy định khả năng mà kiểu phải có; wildcard cho phép người gọi truyền cấu trúc dữ liệu với mức linh hoạt phù hợp hướng đọc/ghi.

## 2. Bắt đầu từ giới hạn thật của miền bài toán

Khai báo hợp đồng có mã định danh:

```java
public interface Identified<ID> {
    ID id();
}
```

Kho dùng hai tham số kiểu:

```java
public final class Repository<ID, T extends Identified<ID>> {
    // ...
}
```

Đọc chữ ký từ trái sang phải:

- `ID` là kiểu mã định danh.
- `T` là kiểu phần tử mà kho lưu.
- `T extends Identified<ID>` yêu cầu phần tử có phương thức `id()` trả đúng `ID`.

`extends` trong giới hạn tham số kiểu dùng cả khi giới hạn là một interface. Không viết `T implements Identified<ID>`.

Nếu `Book` có mã kiểu `String`, thì `Repository<String, Book>` hợp lệ còn `Repository<Integer, Book>` không phù hợp giới hạn. Quan hệ này được kiểm tra trước khi chạy.

Không thêm một giới hạn chỉ vì có thể thêm. Chẳng hạn, kho không sắp xếp phần tử thì không cần ép mọi `T` triển khai `Comparable`. Giới hạn càng chặt càng thu hẹp số kiểu có thể dùng API.

Hợp đồng biến kiểu và giới hạn được quy định trong [JLS mục 4.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4).

## 3. Vì sao List<Book> không phải List<Product>?

Giả sử `Book extends Product`. Một `Book` có thể được dùng ở nơi cần một `Product`, nhưng quan hệ đó không làm `List<Book>` thành kiểu con của `List<Product>`.

Nếu phép gán sau được cho phép:

```java
// Không biên dịch; đây là ví dụ sai có chủ đích.
List<Book> books = new ArrayList<>();
List<Product> products = books;
products.add(new Product("p1", "Mouse"));
```

thì danh sách mà người dùng tưởng chỉ chứa sách sẽ nhận được sản phẩm không phải sách.

Java tránh lỗ hổng này bằng tính bất biến của tham số kiểu trong trường hợp trên. Muốn chấp nhận nguồn chứa kiểu con mà không cho ghi tùy ý, cần dùng wildcard phù hợp.

Không giải quyết bằng cách ép `List<Book>` thành `List<Product>`, chuyển sang `List` thô hoặc tắt cảnh báo. Cần sửa hợp đồng của API theo điều nó thực sự cần làm.

## 4. Chọn wildcard theo luồng dữ liệu

### 4.1. Nguồn cung cấp phần tử: ? extends T

Kho nhập nhiều phần tử nhưng không thêm phần tử vào nguồn:

```java
public void upsertAll(Iterable<? extends T> source)
```

Nếu kho lưu `Product`, nguồn có thể là `Iterable<Product>` hoặc `Iterable<Book>`. Khi lặp, có thể đọc từng phần tử như `T`.

`? extends T` biểu thị một kiểu chưa biết nhưng là `T` hoặc kiểu con. Vì kiểu cụ thể chưa biết, không thể an toàn thêm một `Product` tùy ý qua tham chiếu `List<? extends Product>`: danh sách thật có thể chỉ nhận `Book`.

### 4.2. Đích nhận phần tử: ? super T

Kho muốn thêm các phần tử `T` vào đích:

```java
public void copyInto(Collection<? super T> destination)
```

Nếu kho lưu `Book`, đích có thể là `Collection<Book>`, `Collection<Product>` hoặc `Collection<Object>`.

Qua tham chiếu `Collection<? super Book>`, ta biết thêm một `Book` là phù hợp về kiểu. Khi đọc phần tử từ một `List<? super Book>`, kiểu chắc chắn chung chỉ là `Object`: danh sách thật có thể chứa các đối tượng khác nếu nó là `List<Object>`.

### 4.3. PECS là cách nhớ, không phải công thức áp cho mọi tham số

Quy tắc thường gọi **PECS**:

- Producer extends: nguồn cung cấp phần tử dùng `extends`.
- Consumer super: nơi nhận phần tử dùng `super`.

“Cung cấp/nhận” phải được xét **so với API đang thiết kế**. Một tham số vừa đọc vừa ghi với cùng kiểu cụ thể thường cần `List<T>`, không tự động đổi mọi thứ thành wildcard.

Wildcard cũng không tạo tính bất biến của dữ liệu. `List<? extends Product>` vẫn có thể có thao tác xóa nếu danh sách hỗ trợ; một tham chiếu khác vẫn có thể sửa cấu trúc. Nó không tương đương danh sách không sửa được.

Các quy tắc wildcard nằm trong [JLS mục 4.5.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1). Một ví dụ thực trong thư viện chuẩn là chữ ký `Collections.copy(List<? super T>, List<? extends T>)` trong [Collections API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html). Phương thức đó thay phần tử ở đích đã có kích thước phù hợp; không nhầm nó với thao tác nối thêm của bài này.

## 5. Khi nào dùng tên kiểu R thay vì một dấu hỏi khác?

Kho cần chuyển từng `T` thành một kiểu kết quả rồi thêm kết quả đó vào đích:

```java
public <R> void mapInto(
        Function<? super T, ? extends R> mapper,
        Collection<? super R> destination)
```

`R` là một tham số kiểu của phương thức, không phải của toàn bộ kho. Mỗi lần gọi có thể suy luận một `R` khác nhau.

Tách chữ ký:

| Vị trí | Lý do |
| --- | --- |
| `? super T` ở đầu vào hàm | Hàm nhận được `T` hoặc kiểu cha của `T` đều xử lý được phần tử kho |
| `? extends R` ở đầu ra hàm | Kết quả là `R` hoặc kiểu con đều dùng được như `R` |
| `? super R` ở đích | Đích phải nhận được kết quả kiểu `R` |

Ví dụ, kho sách có thể dùng một `Function<Product, String>` để lấy tiêu đề, rồi ghi chuỗi vào `List<CharSequence>`. Hàm biết xử lý mọi sản phẩm nên cũng xử lý được sách; chuỗi là một `CharSequence`.

Dùng `R` giúp nối quan hệ kiểu giữa kết quả hàm và đích. Hai dấu `?` độc lập không có nghĩa cùng một kiểu chưa biết.

`Function<T,R>` là giao diện nhận một đối số và tạo kết quả, được định nghĩa trong [Function API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html).

## 6. Lời giải Java 17+ chạy đầy đủ

Quy ước hành vi của kho:

- Phần tử và mã định danh không được `null`.
- `upsert` thêm mới hoặc thay đối tượng có cùng mã.
- Thứ tự duyệt là thứ tự mã được thêm lần đầu, nhờ `LinkedHashMap`.
- `snapshot()` trả danh sách không sửa được về cấu trúc.
- Kho không cung cấp đồng bộ cho nhiều luồng.

Lưu thành `GenericApiDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

public class GenericApiDemo {
    public interface Identified<ID> {
        ID id();
    }

    public static class Product implements Identified<String> {
        private final String id;
        private final String title;

        public Product(String id, String title) {
            this.id = Objects.requireNonNull(id);
            this.title = Objects.requireNonNull(title);
        }

        @Override
        public String id() {
            return id;
        }

        public String title() {
            return title;
        }

        @Override
        public String toString() {
            return id + ":" + title;
        }
    }

    public static final class Book extends Product {
        public Book(String id, String title) {
            super(id, title);
        }
    }

    public static final class Repository<ID, T extends Identified<ID>> {
        private final Map<ID, T> values = new LinkedHashMap<>();

        public void upsert(T value) {
            Objects.requireNonNull(value);
            values.put(Objects.requireNonNull(value.id()), value);
        }

        public void upsertAll(Iterable<? extends T> source) {
            Objects.requireNonNull(source);
            for (T value : source) {
                upsert(value);
            }
        }

        public Optional<T> find(ID id) {
            return Optional.ofNullable(
                    values.get(Objects.requireNonNull(id)));
        }

        public void copyInto(Collection<? super T> destination) {
            Objects.requireNonNull(destination);
            destination.addAll(values.values());
        }

        public <R> void mapInto(
                Function<? super T, ? extends R> mapper,
                Collection<? super R> destination) {
            Objects.requireNonNull(mapper);
            Objects.requireNonNull(destination);
            for (T value : values.values()) {
                destination.add(mapper.apply(value));
            }
        }

        public List<T> snapshot() {
            return List.copyOf(values.values());
        }
    }

    public static void main(String[] args) {
        List<Book> books = List.of(
                new Book("b1", "Generics"),
                new Book("b2", "Concurrency"));

        Repository<String, Product> catalog = new Repository<>();
        catalog.upsertAll(books);
        catalog.upsert(new Product("p1", "Mouse"));
        catalog.upsert(new Book("b1", "Generics revised"));
        System.out.println("catalog=" + catalog.snapshot());
        System.out.println("found=" + catalog.find("b2").orElseThrow());

        List<Object> exported = new ArrayList<>();
        catalog.copyInto(exported);
        System.out.println("exported=" + exported);

        Repository<String, Book> bookCatalog = new Repository<>();
        bookCatalog.upsertAll(books);
        Function<Product, String> titleOf = Product::title;
        List<CharSequence> titles = new ArrayList<>();
        bookCatalog.mapInto(titleOf, titles);
        System.out.println("titles=" + titles);
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror GenericApiDemo.java
java GenericApiDemo
```

Stdout:

```text
catalog=[b1:Generics revised, b2:Concurrency, p1:Mouse]
found=b2:Concurrency
exported=[b1:Generics revised, b2:Concurrency, p1:Mouse]
titles=[Generics, Concurrency]
```

Trong lệnh biên dịch, `-Xlint:all` bật các cảnh báo lint và `-Werror` làm cảnh báo trở thành lỗi. Mục đích là không để lời giải che kiểu thô hoặc phép chuyển đổi không kiểm chứng.

### Đọc các lời gọi thành công

`catalog.upsertAll(books)` thành công dù danh mục lưu `Product`, vì nguồn có kiểu phần tử con `Book`.

`catalog.copyInto(exported)` thành công dù đích là `List<Object>`, vì đích nhận được mọi `Product`.

`bookCatalog.mapInto(titleOf, titles)` dùng hàm nhận `Product` để xử lý `Book`, và đưa kết quả chuỗi vào danh sách `CharSequence`. Đây là nơi cả hai chiều wildcard của hàm phát huy tác dụng.

Lần thay mã `b1` đổi đối tượng được lưu nhưng không đổi thứ tự mã đã có. Sách trong danh sách `books` ban đầu không bị thay bằng đối tượng mới trong kho thứ nhất, nên danh mục sách riêng vẫn tạo tiêu đề `Generics`.

## 7. Dùng ca không biên dịch để kiểm tra hợp đồng API

Tạo tệp riêng `NegativeGenericExamples.java`, đặt cùng thư mục với lời giải. Tệp sau **cố ý không biên dịch**:

```java
import java.util.ArrayList;
import java.util.List;

class NegativeGenericExamples {
    void rejected() {
        List<GenericApiDemo.Book> books = new ArrayList<>();
        List<GenericApiDemo.Product> products = books;

        GenericApiDemo.Repository<Integer, GenericApiDemo.Book> wrong;

        List<? extends GenericApiDemo.Product> source = books;
        source.add(new GenericApiDemo.Product("p1", "Mouse"));

        List<? super GenericApiDemo.Book> destination =
                new ArrayList<GenericApiDemo.Product>();
        GenericApiDemo.Book first = destination.get(0);
    }
}
```

Biên dịch hai tệp để kiểm tra:

```shell
javac GenericApiDemo.java NegativeGenericExamples.java
```

Kỳ vọng là biên dịch thất bại vì bốn dòng sai về kiểu:

| Dòng có vấn đề | Vì sao bị từ chối? |
| --- | --- |
| Gán `books` cho `List<Product>` | `List<Book>` không phải `List<Product>` |
| `Repository<Integer, Book>` | `Book` cung cấp mã `String`, không thỏa `Identified<Integer>` |
| `source.add(new Product(...))` | Kiểu phần tử cụ thể của nguồn có thể là `Book` |
| Gán `destination.get(0)` cho `Book` | Giá trị đọc qua `? super Book` không được bảo đảm là sách |

Thông báo chi tiết của `javac` có thể khác theo phiên bản hoặc ngôn ngữ môi trường. Điều cần kiểm chứng là ràng buộc bị từ chối đúng lúc, không phải khớp từng ký tự thông báo lỗi.

Không thêm tệp âm vào lệnh chạy lời giải bình thường. Đó là bằng chứng biên dịch cho những cách dùng mà API cần ngăn.

## 8. Đọc lỗi capture mà không ép kiểu bừa

Trong lỗi wildcard, trình biên dịch có thể hiển thị một tên như `CAP#1`. Có thể hiểu đó là tên tạm cho “kiểu chưa biết cụ thể” của wildcard.

Ví dụ, `List<? extends Product>` có thể là danh sách của một kiểu con cụ thể mà phương thức không biết. Việc đọc ra như `Product` vẫn an toàn, nhưng thêm một `Product` chung có thể không phù hợp với kiểu đó.

Khi gặp lỗi:

1. Xác định tham số đang là nguồn, đích hay vừa đọc vừa ghi.
2. Kiểm tra có cần một tên kiểu để nối quan hệ giữa nhiều tham số không.
3. Chỉ nới wildcard theo đúng các thao tác mà phương thức thực hiện.
4. Không sửa bằng raw type hoặc ép kiểu nếu chưa chứng minh hợp đồng an toàn.

Nếu phương thức cần đọc một phần tử rồi ghi chính phần tử đó trở lại cùng một danh sách wildcard, có thể cần một phương thức trợ giúp generic để trình biên dịch giữ tên cho kiểu được capture. Nhưng bài này không cần thủ thuật đó: các nguồn và đích đã được thiết kế tách theo luồng dữ liệu.

## 9. Những bảo đảm generics không cung cấp

### Đích vẫn phải hỗ trợ thay đổi

`Collection<? super T>` chứng minh sự tương thích về kiểu, không chứng minh có thể thêm phần tử. Truyền một danh sách tạo bởi `List.of(...)` làm đích có thể dẫn tới `UnsupportedOperationException`.

### Snapshot không phải sao chép sâu

`List.copyOf(...)` bảo vệ cấu trúc danh sách trả về; nó không tự sao chép từng đối tượng miền. Trong ví dụ, các trường sản phẩm được giữ cố định. Nếu thay bằng đối tượng có trạng thái thay đổi, người gọi vẫn có thể quan sát thay đổi của đối tượng được tham chiếu.

### Thao tác nhiều phần tử không tự có tính nguyên tử

Nếu nguồn có phần tử lỗi hoặc hàm ánh xạ ném ngoại lệ giữa chừng, các phần tử đã nhập/xuất trước đó có thể đã được thay đổi. Muốn “hoặc hoàn tất toàn bộ hoặc không thay đổi”, phải thiết kế bước kiểm tra/bộ đệm hoặc cơ chế giao dịch riêng.

### Generic không tự làm kho an toàn cho nhiều luồng

`LinkedHashMap` trong lời giải không có bảo đảm đồng bộ cho các lời gọi đồng thời. Phải xác định mô hình truy cập trước khi tái sử dụng trong dịch vụ.

### Kiểu mã định danh phải giữ tính ổn định

Mã dùng làm khóa cần có `equals()/hashCode()` phù hợp và không thay đổi theo cách làm hỏng tra cứu trong khi được giữ làm khóa. Ràng buộc `T extends Identified<ID>` không tự chứng minh được điều kiện hành vi đó.

Đây là ví dụ về ranh giới giữa **tương thích kiểu** và **hợp đồng runtime**. Một API tốt cần cả hai.

## 10. Bài tập mở rộng và tiêu chí tự đánh giá

Thực hiện lần lượt:

1. Thêm `remove(ID id)` trả `Optional<T>`; kiểm tra người gọi không thể truyền nhầm kiểu mã.
2. Thêm `findAll(Predicate<? super T> filter)` trả `List<T>`; thử dùng bộ lọc của `Product` cho kho `Book`.
3. Viết một hàm tiện ích `<T> appendAll(Iterable<? extends T>, Collection<? super T>)` và dùng nó để nối danh sách số nguyên vào `List<Number>`.
4. Thêm kiểm tra khi mapper ném lỗi; ghi rõ đích có bị thay đổi một phần hay không.
5. Thiết kế phiên bản “kiểm tra toàn bộ trước khi nhập” nếu bài toán yêu cầu tránh thay đổi một phần.

Tiêu chí đạt:

- Lời giải chính biên dịch sạch với lint.
- Các trường hợp dùng kiểu con/kiểu cha hợp lệ không cần ép kiểu.
- Các ca âm bị từ chối khi biên dịch.
- Kết quả trả về giữ thông tin kiểu hữu ích, chẳng hạn `Optional<T>` và `List<T>`.
- Không coi wildcard là bằng chứng về bất biến, khả năng sửa, đồng bộ hoặc giao dịch.

## 11. Tự kiểm tra

1. Vì sao dùng giới hạn `T extends Identified<ID>`? **Để nối kiểu phần tử với kiểu mã và cho phép gọi `id()` đúng kiểu.**
2. Vì sao nguồn dùng `? extends T`? **API chỉ cần lấy các phần tử tương thích để nhập.**
3. Vì sao đích dùng `? super T`? **Đích phải nhận được phần tử kiểu T, kể cả khi nó lưu một kiểu cha.**
4. `? extends Product` có làm danh sách bất biến không? **Không.**
5. Vì sao mapInto cần `R`? **Để nối kiểu kết quả của hàm với kiểu mà đích nhận được.**
6. Generic có ngăn được đích không sửa được không? **Không; đó là hợp đồng runtime khác.**
7. Có nên chữa lỗi wildcard bằng một phép ép kiểu không kiểm chứng không? **Không; trước hết cần sửa đúng quan hệ kiểu và hướng sử dụng dữ liệu.**
