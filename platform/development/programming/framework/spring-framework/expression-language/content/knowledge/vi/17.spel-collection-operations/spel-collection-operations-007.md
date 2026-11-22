# Phân biệt collection mutable với kết quả chỉ đọc

Khi làm việc với collection trong Spring Expression Language (SpEL), cần phân biệt **khả năng thay đổi của collection nguồn**, **collection mới do biểu thức tạo ra** và **chính sách read-only của EvaluationContext**. Ba khái niệm này liên quan đến nhau nhưng không đồng nghĩa.

Một collection có thể cho phép thêm, xóa hoặc thay thế phần tử. Một collection khác có thể chỉ cho phép đọc. Trong khi đó, một biểu thức SpEL có thể trả về tham chiếu đến collection nguồn hoặc tạo một collection kết quả mới thông qua selection và projection. Việc dùng context read-only cũng không tự động biến mọi object được trả về thành immutable.

## Mutable collection là gì?

Một collection mutable cho phép thay đổi cấu trúc hoặc nội dung thông qua các thao tác như:

- **add(...)**: thêm phần tử.
- **remove(...)**: xóa phần tử.
- **set(...)**: thay thế phần tử tại một vị trí trong List.
- **put(...)**: thêm hoặc thay thế một entry trong Map.
- **clear()**: xóa toàn bộ phần tử.

Ví dụ với ArrayList:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");

names.add("Chi");
names.set(0, "Anh");
names.remove("Binh");
~~~

Sau các thao tác, collection chứa **Anh** và **Chi**. Những thay đổi này tác động trực tiếp lên object ArrayList đang được tham chiếu.

Một collection read-only hoặc unmodifiable không cho phép caller thực hiện các thao tác ghi thông qua reference đó. Ví dụ:

~~~java
List<String> names = List.of("An", "Binh", "Chi");

// names.add("Dung"); // UnsupportedOperationException
~~~

**List** là interface mô tả cách truy cập danh sách, không bảo đảm implementation có thể thay đổi. Một ArrayList thường mutable, trong khi List.of(...) trả về danh sách không hỗ trợ sửa đổi. Vì vậy, không thể kết luận collection mutable chỉ từ kiểu khai báo List hoặc Collection.

## Read-only view và immutable snapshot

Java có nhiều cách cung cấp collection không cho phép caller sửa đổi, nhưng chúng không có cùng semantics.

### Unmodifiable view

**Collections.unmodifiableList(...)** tạo một wrapper chặn các thao tác ghi thông qua wrapper:

~~~java
List<String> source = new ArrayList<>(
        List.of("An", "Binh"));

List<String> view =
        Collections.unmodifiableList(source);
~~~

Caller không thể gọi **view.add(...)** hoặc **view.remove(...)** thành công. Tuy nhiên, view vẫn đọc từ collection source. Nếu một đoạn code khác sửa source, nội dung quan sát qua view cũng thay đổi:

~~~java
source.add("Chi");

// view lúc này cũng nhìn thấy "Chi"
~~~

Đây là một **read-only view**, không phải snapshot độc lập. Collection nền vẫn mutable và các reference khác vẫn có thể thay đổi nó.

### Unmodifiable snapshot

Nếu muốn tạo một kết quả không cho phép sửa đổi và không phản ánh những lần thay đổi sau đó của collection nguồn, hãy copy trước rồi mới bọc:

~~~java
List<String> snapshot =
        Collections.unmodifiableList(
                new ArrayList<>(source));
~~~

Hoặc dùng **List.copyOf(...)** khi dữ liệu không chứa null:

~~~java
List<String> snapshot = List.copyOf(source);
~~~

List.copyOf tạo một danh sách không hỗ trợ sửa đổi và không theo dõi thay đổi cấu trúc của collection nguồn. Phương thức này không chấp nhận phần tử null.

Với Map, có thể dùng **Collections.unmodifiableMap(new LinkedHashMap<>(source))** để tạo snapshot không cho caller sửa đổi và giữ thứ tự duyệt của LinkedHashMap. **Map.copyOf(...)** cũng tạo Map không hỗ trợ sửa đổi nhưng không chấp nhận key hoặc value null.

Cả hai cách snapshot trên đều là **shallow copy**: collection mới có cấu trúc riêng, nhưng các object được chứa bên trong có thể vẫn là cùng những reference mutable.

## SpEL trả về collection nguồn hay collection mới?

Cần xem biểu thức đang đọc property trực tiếp hay thực hiện collection operation.

### Đọc trực tiếp property

Giả sử root object có property products:

~~~java
public class Catalog {
    private final List<Product> products;

    public Catalog(List<Product> products) {
        this.products = products;
    }

    public List<Product> getProducts() {
        return products;
    }
}
~~~

Nếu đánh giá biểu thức:

~~~java
Expression expression =
        parser.parseExpression("products");

List<Product> result =
        expression.getValue(catalog, List.class);
~~~

SpEL đọc property products và trả về giá trị mà getter cung cấp. Nếu getter trả về chính collection mutable bên trong Catalog, **result và catalog.getProducts() cùng tham chiếu đến một collection**.

Do đó, nếu caller sửa result, collection bên trong Catalog cũng bị sửa:

~~~java
result.add(new Product("Keyboard"));
~~~

Đây là thay đổi trên collection nguồn vì không có collection mới được tạo ra trong phép đọc property này.

Nếu không muốn expose trực tiếp collection nội bộ, hãy trả về một view hoặc snapshot phù hợp từ getter, hoặc tạo một DTO chỉ chứa dữ liệu cần đọc.

## Selection tạo collection kết quả mới

Selection dùng cú pháp **.?[condition]** để lọc phần tử:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);
~~~

SpEL đánh giá điều kiện trên từng phần tử và trả về một collection mới chứa các phần tử phù hợp. Với selection trên Map, kết quả là một Map mới chứa các entry được chọn.

Tài liệu Spring mô tả selection là thao tác tạo collection mới chứa tập con của dữ liệu nguồn. Tuy nhiên, hợp đồng tài liệu không tuyên bố mọi collection kết quả đều là unmodifiable. Không nên dựa vào việc có thể gọi add, remove hoặc put trên kết quả nếu chưa kiểm soát implementation thực tế.

Điểm quan trọng khác là **collection mới không có nghĩa các phần tử bên trong cũng được copy**. Selection giữ lại các phần tử được chọn từ nguồn. Nếu phần tử là Product mutable, result và source vẫn tham chiếu đến cùng Product đó.

Ví dụ:

~~~java
Product product = catalog.getProducts().get(0);

List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

selected.get(0).setName("Updated name");
~~~

Nếu selected chứa chính product ban đầu, thay đổi name sẽ được nhìn thấy qua collection nguồn vì object Product được chia sẻ. Việc tạo collection mới chỉ tách **container**, không tự tạo bản sao sâu của các phần tử.

## Projection tạo collection từ giá trị biểu thức

Projection dùng cú pháp **.![expression]** để tính một giá trị cho từng phần tử và thu thập các kết quả:

~~~java
List<String> names =
        parser.parseExpression("products.![name]")
                .getValue(catalog, List.class);
~~~

Trong ví dụ, projection tạo List tên sản phẩm. Các phần tử kết quả là String, nên caller không thể dùng chúng để thay đổi property name của Product ban đầu.

Nếu projection trả về chính object hiện tại:

~~~java
List<Product> sameProducts =
        parser.parseExpression("products.![#this]")
                .getValue(catalog, List.class);
~~~

List container là mới, nhưng các phần tử vẫn là reference đến Product trong collection nguồn. Nếu projection trả về một property chứa object mutable, các reference đó cũng có thể được chia sẻ.

Với projection trên Map, SpEL đánh giá biểu thức trên từng Map.Entry và tạo một List các kết quả. Đây là một collection mới; nó không phải Map gốc và cũng không tự động giữ lại key-value mapping ban đầu.

## Phân biệt ba trường hợp

| Biểu thức hoặc thao tác | Container kết quả | Quan hệ với nguồn |
|---|---|---|
| **products** | Reference đến collection do getter trả về | Có thể chính là collection nguồn |
| **products.?[active]** | Collection mới chứa phần tử được chọn | Container tách biệt; phần tử có thể dùng chung reference |
| **products.![name]** | Collection mới chứa giá trị projection | Container tách biệt; giá trị có thể là object mới hoặc reference có sẵn |
| **Collections.unmodifiableList(source)** | Wrapper read-only | Vẫn nhìn thấy thay đổi của source |
| **Collections.unmodifiableList(new ArrayList<>(source))** | Snapshot read-only | Cấu trúc độc lập; phần tử vẫn có thể mutable |

Spring Reference mô tả selection và projection là các thao tác trả về collection mới. Selection giữ lại phần tử phù hợp; projection tạo một giá trị cho mỗi phần tử. Hãy phân biệt điều đó với việc đọc trực tiếp một property collection. Xem thêm [Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html) và [Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html).

## SimpleEvaluationContext read-only không đóng băng collection

**SimpleEvaluationContext.forReadOnlyDataBinding()** cấu hình truy cập property theo hướng chỉ đọc. Mục đích là giới hạn khả năng gán property thông qua SpEL trong context đó.

Ví dụ:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("products");

List<Product> products =
        expression.getValue(context, catalog, List.class);
~~~

Việc sử dụng read-only data binding không tự động:

- Copy collection được trả về.
- Bọc collection bằng Collections.unmodifiableList hoặc Collections.unmodifiableMap.
- Chuyển các phần tử thành object immutable.
- Tạo một deep copy của object graph.
- Ngăn code Java bên ngoài sửa một collection mutable mà nó đang giữ reference.

Nói cách khác, **read-only EvaluationContext là chính sách truy cập của SpEL**, còn mutability là đặc tính của object Java được trả về. Hai lớp bảo vệ này cần được thiết kế riêng.

Tài liệu Spring cũng lưu ý rằng read-only data binding kiểm soát việc gán property, nhưng không tự xác minh rằng một accessor được gọi khi đọc property là thuần và không có side effect. Vì vậy, object được expose cho biểu thức vẫn cần có API phù hợp với mức tin cậy của biểu thức.

## Cách tạo kết quả mutable có chủ đích

Nếu cần chỉnh sửa tập phần tử được selection, hãy tạo bản copy có thể thay đổi:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

List<Product> editable =
        new ArrayList<>(selected);

editable.add(new Product("New product"));
~~~

Ở đây, editable là ArrayList do ứng dụng chủ động tạo. Thêm hoặc xóa phần tử trong editable không làm thay đổi cấu trúc collection products trong Catalog.

Tuy nhiên, các Product trong editable vẫn có thể là những object ban đầu. Nếu cần thay đổi property mà không ảnh hưởng nguồn, phải copy từng Product hoặc chuyển chúng thành DTO/value object mới.

## Cách tạo kết quả read-only có chủ đích

Nếu muốn cung cấp kết quả cho tầng khác chỉ để đọc, hãy tạo snapshot rồi bọc nó:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

List<Product> readOnlySnapshot =
        Collections.unmodifiableList(
                new ArrayList<>(selected));
~~~

Caller không thể thêm hoặc xóa phần tử qua readOnlySnapshot. Cấu trúc snapshot cũng không thay đổi khi collection nguồn được thêm hoặc xóa phần tử sau đó.

Nhưng nếu Product vẫn mutable, caller có thể gọi setter trên một Product được lấy từ snapshot. Nếu cần bảo vệ cả trạng thái phần tử, hãy ánh xạ sang DTO immutable hoặc copy sâu theo cấu trúc dữ liệu của ứng dụng:

~~~java
List<ProductView> views = selected.stream()
        .map(product -> new ProductView(
                product.getId(),
                product.getName()))
        .toList();
~~~

Ví dụ này tạo các ProductView chỉ chứa dữ liệu cần hiển thị. Để bảo đảm immutable, bản thân ProductView và các trường lồng bên trong cũng phải được thiết kế phù hợp.

## Lưu ý với Kotlin

Trong Kotlin, **List<T>** là interface read-only ở mức API ngôn ngữ, còn **MutableList<T>** cung cấp các thao tác thêm, xóa và thay thế. Tuy nhiên, một List<T> có thể được backed bởi một collection mutable mà code khác vẫn giữ reference.

Vì vậy, khai báo biến bằng List<T> giúp giới hạn các thao tác mà đoạn code Kotlin có thể gọi trực tiếp, nhưng không nhất thiết tạo ra một immutable snapshot. Nếu cần snapshot không thay đổi, hãy copy sang collection không hỗ trợ sửa đổi hoặc dùng kiểu dữ liệu immutable phù hợp.

## Những lỗi thiết kế thường gặp

- **Cho rằng List luôn mutable:** List chỉ là interface; implementation có thể mutable hoặc unmodifiable.
- **Cho rằng kết quả selection/projection là read-only:** Spring mô tả kết quả là collection mới, nhưng không cam kết nó là immutable.
- **Cho rằng collection mới đồng nghĩa object mới:** selection thường giữ nguyên phần tử được chọn; projection có thể trả lại reference của phần tử.
- **Nhầm read-only context với immutable data:** SimpleEvaluationContext giới hạn khả năng của SpEL, không đóng băng object graph.
- **Dùng unmodifiable view nhưng vẫn để lộ collection nền:** code khác có thể thay đổi collection nguồn và làm view thay đổi theo.
- **Chỉ copy container nhưng bỏ qua phần tử mutable:** snapshot cấu trúc không bảo đảm trạng thái các object lồng nhau bất biến.

## Kết luận

Khi dùng collection trong SpEL, hãy xác định rõ biểu thức đang trả về reference của collection nguồn hay tạo một collection kết quả mới. Đọc property trực tiếp có thể trả về chính collection mutable của object. Selection và projection tạo collection mới, nhưng không tự động deep-copy phần tử hoặc cam kết kết quả là unmodifiable.

**SimpleEvaluationContext.forReadOnlyDataBinding()** giới hạn việc gán property qua SpEL; nó không biến collection được trả về thành immutable. Nếu cần chỉnh sửa, hãy tạo ArrayList hoặc Map copy rõ ràng. Nếu cần kết quả chỉ đọc, hãy tạo snapshot rồi bọc bằng API unmodifiable hoặc dùng collection immutable phù hợp. Khi phần tử bên trong còn mutable, cần DTO immutable hoặc copy sâu để bảo vệ toàn bộ dữ liệu.
