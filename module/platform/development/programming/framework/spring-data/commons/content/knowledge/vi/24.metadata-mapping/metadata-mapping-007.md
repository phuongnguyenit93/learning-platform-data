# TypeInformation, generic, collection và map

Một thuộc tính được khai báo là `List<Product>` mang nhiều thông tin hơn lớp `List.class`. Hạ tầng ánh xạ cần biết không chỉ đây là một collection, mà còn kiểu phần tử là gì. Với `Map<String, List<Product>>`, nó cần phân biệt kiểu key, kiểu value và kiểu phần tử bên trong value.

Spring Data Commons cung cấp `TypeInformation<T>` để biểu diễn và phân giải những thông tin kiểu đó. Abstraction này giúp metadata giữ ngữ cảnh generic thay vì chỉ xử lý raw class. Tuy nhiên, nó không khôi phục tùy ý những thông tin đã không còn trong khai báo Java và không thay thế cơ chế mapping của từng store.

Bài học tập trung vào đọc kiểu thuộc tính, phân giải generic qua kế thừa, xử lý collection, array và map, đồng thời phân biệt kiểu Java với khả năng lưu trữ thực tế.

## 1. Vì sao chỉ dùng Class chưa đủ?

Xét các khai báo:

```java
List<Product> products;
List<String> labels;
Map<String, Product> byCode;
```

Nếu chỉ nhìn raw class, hai thuộc tính đầu đều có kiểu `List`. `Map.class` cũng không cho biết key là String hay value là Product.

Java có cơ chế type erasure, nhưng điều đó không có nghĩa mọi thông tin generic trong mã khai báo đều biến mất. Chữ ký generic của field, method hoặc lớp cha vẫn có thể được phản chiếu và phân giải trong một ngữ cảnh phù hợp.

Cần phân biệt:

| Nguồn thông tin | Có thể biết gì? |
| --- | --- |
| `object.getClass()` của một danh sách thông thường | Runtime class, chẳng hạn ArrayList |
| `List.class` | Raw interface List |
| Field được khai báo `List<Product>` | Raw type và generic argument trong khai báo |
| Một lớp con cố định tham số của lớp cha | Cách type variable của lớp cha được gắn với kiểu cụ thể |

`TypeInformation` phục vụ việc sử dụng và phân giải những thông tin có sẵn đó. Nó không đoán kiểu danh sách bằng cách lấy phần tử đầu tiên, nên vẫn có thể mô tả thuộc tính dù collection đang rỗng hoặc chưa có instance.

## 2. Các API cần nắm

Interface nằm trong package:

```java
import org.springframework.data.util.TypeInformation;
```

Ví dụ tạo metadata từ một domain class:

```java
TypeInformation<Catalog> catalogType = TypeInformation.of(Catalog.class);
```

Những thao tác thường dùng:

| Phương thức | Vai trò |
| --- | --- |
| `getType()` | Lấy raw class của kiểu đang xét |
| `getProperty(name)` | Tìm thông tin kiểu của thuộc tính; có thể không tìm thấy |
| `getRequiredProperty(name)` | Tìm thuộc tính bắt buộc; báo lỗi nếu không tìm thấy |
| `isCollectionLike()` | Nhận diện kiểu collection-like mà implementation hỗ trợ, gồm các trường hợp thông dụng như List, Set và array |
| `isMap()` | Nhận diện kiểu map |
| `getComponentType()` | Lấy kiểu phần tử collection/array hoặc kiểu key của map |
| `getMapValueType()` | Lấy kiểu value của map |
| `getActualType()` | Lấy kiểu có ý nghĩa sau một mức container: phần tử collection/array hoặc value của map |
| `getTypeArguments()` | Lấy các đối số generic của kiểu trong ngữ cảnh đang xét |
| `getSuperTypeInformation(superType)` | Xem thông tin kiểu ở một supertype phù hợp, giữ ngữ cảnh generic |

Các phương thức trả về component, map value hoặc actual type có thể không cung cấp được kiểu như người gọi mong đợi nếu metadata không đủ. Không gọi chuỗi phương thức trên một kết quả nullable mà chưa xử lý hợp đồng tương ứng.

API cũng có các biến thể required cho component và map value. Chỉ dùng chúng khi cấu trúc kiểu đã được kiểm tra hoặc được hợp đồng của thành phần bảo đảm; biến thể required không tự bổ sung thông tin generic bị thiếu.

### Điểm dễ nhầm nhất

Với map:

```text
getComponentType() -> kiểu KEY
getMapValueType()  -> kiểu VALUE
getActualType()   -> kiểu VALUE
```

Không dùng component type của map như thể đó là value type.

## 3. Mô hình minh họa cho các ví dụ

Các lớp sau là POJO để minh họa introspection kiểu Java. Chúng không cần được lưu vào store để có thể đọc `TypeInformation`.

```java
import java.math.BigDecimal;

public class Product {
    private String code;
    private BigDecimal price;
}
```

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class Catalog {
    private Product featured;
    private List<Product> products;
    private Set<String> labels;
    private Product[] recent;
    private Map<String, Product> byCode;
    private Map<String, List<Product>> groups;
    private List<List<Product>> matrix;
}
```

Không cần tạo `Catalog` và gán dữ liệu thật để đọc những kiểu đã được khai báo trên các field này. Việc đọc metadata kiểu khác với việc truy cập giá trị field trên một object.

Những đoạn tiếp theo giả định các lớp nằm trong phạm vi có thể tham chiếu lẫn nhau và đã import `TypeInformation`.

## 4. Đọc thuộc tính và raw type

```java
TypeInformation<Catalog> catalogType = TypeInformation.of(Catalog.class);

TypeInformation<?> featuredType =
    catalogType.getRequiredProperty("featured");

TypeInformation<?> productsType =
    catalogType.getRequiredProperty("products");

Class<?> featuredClass = featuredType.getType();
Class<?> productsClass = productsType.getType();
```

Ý nghĩa kết quả:

```text
featuredClass = Product.class
productsClass = List.class
```

`productsType` vẫn chứa ngữ cảnh để tiếp tục lấy kiểu phần tử. Nhưng `productsType.getType()` chỉ là raw class, nên không thể phân biệt `List<Product>` với `List<String>` bằng riêng giá trị đó.

### Nullable và required khi tìm thuộc tính

```java
TypeInformation<?> missing = catalogType.getProperty("unknownProperty");
```

Khi không tìm thấy thuộc tính, phương thức có thể trả null. Nếu thuộc tính là một yêu cầu bắt buộc của tiện ích, dùng `getRequiredProperty(...)` để làm rõ giả định thay vì để một lỗi null xuất hiện ở bước sau.

Tên ở đây là tên thuộc tính Java. Nó không phải tên cột SQL, alias projection hay tên field vật lý đã được store đổi tên.

### Thuộc tính lồng nhau dạng scalar

Có thể đi qua một đối tượng có cấu trúc:

```java
TypeInformation<?> codeType =
    catalogType.getRequiredProperty("featured.code");
```

Đường dẫn này đi từ `Catalog.featured` tới `Product.code`. Với collection và map, nên làm rõ bước đi vào phần tử hoặc value thay vì giả định mọi dạng property path tự loại bỏ mọi lớp container.

## 5. Collection và array: lấy kiểu phần tử

### 5.1. List và Set

```java
TypeInformation<?> productsType =
    catalogType.getRequiredProperty("products");

if (productsType.isCollectionLike()) {
    TypeInformation<?> elementType = productsType.getRequiredComponentType();
    Class<?> elementClass = elementType.getType();
}
```

Trong mô hình đã cho, phần tử là `Product`. Tương tự, component type của `Set<String>` là `String`.

`isCollectionLike()` là bước phân loại. `getComponentType()` hoặc biến thể required mới là bước lấy thông tin kiểu phần tử. Biết raw type là List chưa đủ để biết kiểu phần tử cụ thể đã được phân giải hay chưa.

### 5.2. Array

```java
TypeInformation<?> recentType =
    catalogType.getRequiredProperty("recent");

TypeInformation<?> recentElement = recentType.getRequiredComponentType();
```

Với `Product[]`, component type là Product. Với array primitive, component type có thể là một primitive class tương ứng; không đồng nhất mọi kiểu phần tử với một class object tham chiếu thông thường.

### 5.3. Tiếp tục đọc thuộc tính của phần tử

Để tìm kiểu thuộc tính `code` của các phần tử trong `products`:

```java
TypeInformation<?> productType = catalogType
    .getRequiredProperty("products")
    .getRequiredComponentType();

TypeInformation<?> codeType = productType.getRequiredProperty("code");
```

Đoạn mã thể hiện rõ hai bước: đi vào phần tử List, sau đó đọc thuộc tính Product. Nó không phụ thuộc việc collection có dữ liệu hay không.

## 6. Map có hai nhánh kiểu độc lập

Với `Map<String, Product>`:

```java
TypeInformation<?> mapType =
    catalogType.getRequiredProperty("byCode");

if (!mapType.isMap()) {
    throw new IllegalStateException("Mong đợi kiểu Map");
}

TypeInformation<?> keyType = mapType.getRequiredComponentType();
TypeInformation<?> valueType = mapType.getRequiredMapValueType();
```

Ý nghĩa:

```text
mapType.getType() = Map.class
keyType.getType() = String.class
valueType.getType() = Product.class
```

Map không nên được xử lý như một collection chỉ có một kiểu phần tử. Nếu một công cụ metadata chỉ giữ “component” của mọi container, nó có thể vô tình giữ String và bỏ mất Product.

### Value của map cũng có thể là container

Với `Map<String, List<Product>>`:

```java
TypeInformation<?> groupsType =
    catalogType.getRequiredProperty("groups");

TypeInformation<?> groupKeyType = groupsType.getRequiredComponentType();
TypeInformation<?> groupValueType = groupsType.getRequiredMapValueType();
TypeInformation<?> productType = groupValueType.getRequiredComponentType();
```

Cấu trúc tương ứng:

```text
Map
├── key: String
└── value: List
    └── element: Product
```

`groupValueType.getType()` là `List.class`, không phải Product.class. Muốn đi tới Product phải xử lý thêm một mức collection.

Không dùng chỉ số tùy ý trong `getTypeArguments()` để thay thế mọi thao tác map. Với lớp con có generic riêng, thứ tự đối số của lớp con chưa chắc đồng nhất với vị trí key/value của Map mà nó kế thừa.

## 7. getActualType chỉ đi qua một mức cấu trúc

`getActualType()` thuận tiện khi muốn biết kiểu được chứa mà không cần viết riêng nhánh map và collection. Nhưng việc tiện lợi này không có nghĩa nó làm phẳng toàn bộ cấu trúc lồng nhau.

Với các khai báo cụ thể và đủ metadata:

| Kiểu đang xét | Component type | Map value type | Actual type sau một mức |
| --- | --- | --- | --- |
| `Product` | Không có ý nghĩa phần tử | Không có | Product |
| `List<Product>` | Product | Không có | Product |
| `Product[]` | Product | Không có | Product |
| `Map<String, Product>` | String | Product | Product |
| `Map<String, List<Product>>` | String | List<Product> | List<Product> |
| `List<List<Product>>` | List<Product> | Không có | List<Product> |

Với map, actual type giúp đi vào value nhưng không thay cho thông tin key. Nếu đang xây một cây metadata, phải giữ cả hai nhánh chứ không chỉ lặp `getActualType()` rồi bỏ các kiểu trung gian.

### Không đồng nhất mọi wrapper với collection

Không tự suy ra một kiểu wrapper bất kỳ, một reactive publisher hoặc một kiểu tùy chỉnh đều có cùng cách bóc lớp như List. Phải xem khả năng nhận diện container và những abstraction chuyên biệt mà phiên bản cùng module đang sử dụng cung cấp.

Khi viết tiện ích chỉ cho List, Set, array và Map, nên công bố phạm vi đó thay vì hứa xử lý mọi kiểu có thể chứa một giá trị.

## 8. Giữ ngữ cảnh generic qua kế thừa

Xét một lớp generic:

```java
import java.util.List;
import java.util.Map;

public class Envelope<T> {
    private List<T> entries;
    private Map<String, T> byCode;
}
```

Một lớp con cố định T:

```java
public class ProductEnvelope extends Envelope<Product> {
}
```

Đọc kiểu trong ngữ cảnh lớp con:

```java
TypeInformation<ProductEnvelope> envelopeType =
    TypeInformation.of(ProductEnvelope.class);

TypeInformation<?> entriesType =
    envelopeType.getRequiredProperty("entries");

TypeInformation<?> entryType = entriesType.getRequiredComponentType();

TypeInformation<?> indexedValueType = envelopeType
    .getRequiredProperty("byCode")
    .getRequiredMapValueType();
```

Thông tin lớp con cho phép liên kết T với Product. Nếu chỉ dùng raw `Envelope.class`, ngữ cảnh cố định T là Product không còn được cung cấp bởi lời gọi đó.

### Có thể xem kiểu cha trong ngữ cảnh đã phân giải

```java
TypeInformation<?> baseType =
    envelopeType.getSuperTypeInformation(Envelope.class);

if (baseType != null) {
    List<TypeInformation<?>> arguments = baseType.getTypeArguments();
}
```

Đoạn mã cần import `java.util.List`. Ý nghĩa là xem Envelope như một phần của ProductEnvelope, thay vì tạo metadata mới cho raw Envelope rồi mong biết kiểu T của mọi lớp con.

Đây cũng là lý do không nên biến một `TypeInformation` đã phân giải thành `getType()`, sau đó tạo lại TypeInformation từ raw class mà không xét mất mát ngữ cảnh. Raw class không mang toàn bộ thông tin generic của đối tượng metadata trước đó.

### Map kế thừa generic

```java
import java.util.LinkedHashMap;

public class ProductIndex extends LinkedHashMap<String, Product> {
    private static final long serialVersionUID = 1L;
}
```

Có thể phân tích như map qua thông tin kiểu cha:

```java
TypeInformation<ProductIndex> indexType =
    TypeInformation.of(ProductIndex.class);

TypeInformation<?> keyType = indexType.getRequiredComponentType();
TypeInformation<?> valueType = indexType.getRequiredMapValueType();
```

Lớp ProductIndex không tự khai báo hai tham số generic của riêng nó. Vì vậy, không thiết kế thuật toán với giả định “mọi map luôn có đúng hai phần tử trực tiếp trong getTypeArguments của lớp đang xét”. Dùng API map giúp thể hiện đúng ý định phân giải key và value.

## 9. Raw type, wildcard và type variable chưa được cố định

`TypeInformation` không thể tạo lại một hợp đồng cụ thể mà khai báo không cung cấp.

### 9.1. Raw collection

```java
@SuppressWarnings("rawtypes")
public class LegacyCatalog {
    private List products;
}
```

Khai báo này không nói rằng phần tử là Product. Dù tất cả dữ liệu hiện tại đều chứa Product, metadata kiểu không nên coi việc đó là bằng chứng của generic declaration.

Tùy dạng khai báo và cách phân giải, một kết quả có thể chỉ phản ánh Object hoặc không cung cấp được component như người gọi mong muốn. Điều cần giữ là không biến thông tin chưa rõ thành một kiểu miền cụ thể bằng ép kiểu tùy ý.

### 9.2. Wildcard

```java
List<?> unknownItems;
List<? extends Product> productViews;
List<? super Product> productTargets;
```

Các khai báo biểu đạt những ràng buộc khác nhau:

| Khai báo | Điều không được suy ra |
| --- | --- |
| `List<?>` | Không biết một kiểu phần tử miền cụ thể chỉ từ wildcard |
| `List<? extends Product>` | Biết ràng buộc phía trên, không biết mọi phần tử đều có đúng runtime class Product |
| `List<? super Product>` | Không đồng nhất kiểu phần tử đọc ra với đúng Product chỉ vì có lower bound Product |

Kiểu được công cụ phân giải từ bound cần được hiểu là thông tin ràng buộc trong ngữ cảnh. Nó không tự liệt kê tất cả subtype thực tế có thể xuất hiện trong dữ liệu.

### 9.3. Type variable chưa được cố định

Nếu thành phần chỉ nhận raw class của một lớp `Envelope<T>`, không có ngữ cảnh nào gắn T với Product thì không thể mặc định T là Product.

Với T có bound, metadata có thể cho biết bound hoặc thông tin đã phân giải từ nó. Bound không đồng nghĩa đã biết một subtype cụ thể cho mọi instance.

### 9.4. Generic không kiểm tra dữ liệu thực tế

Một collection bị đưa dữ liệu sai kiểu qua raw API hoặc thao tác không an toàn vẫn có thể không đúng với metadata khai báo. TypeInformation không tự duyệt từng phần tử để validation.

Nó cũng không bảo đảm collection khác null, không rỗng hay không chứa phần tử null. Những yêu cầu đó thuộc validation, mapping và quy tắc nghiệp vụ tương ứng.

## 10. Dùng cùng metadata ánh xạ

Trong hạ tầng Spring Data, một `PersistentProperty` có thể cung cấp thông tin kiểu:

```java
TypeInformation<?> propertyType = persistentProperty.getTypeInformation();
```

`persistentProperty` là metadata của thuộc tính do module quản lý. Từ đó, một thành phần dùng chung có thể phân loại:

```java
if (propertyType.isMap()) {
    TypeInformation<?> keyType = propertyType.getComponentType();
    TypeInformation<?> valueType = propertyType.getMapValueType();
    // Giữ cả nhánh key và value theo hợp đồng của thành phần.
} else if (propertyType.isCollectionLike()) {
    TypeInformation<?> elementType = propertyType.getComponentType();
    // Xử lý kiểu phần tử nếu phân giải được.
} else {
    Class<?> scalarType = propertyType.getType();
    // Xử lý kiểu không phải container trong phạm vi đang hỗ trợ.
}
```

Đặt nhánh map riêng làm ý định rõ ràng: map có key và value. Với bất kỳ kết quả nullable nào, code thực tế phải quyết định cho phép kiểu chưa rõ, yêu cầu cấu hình bổ sung hay báo lỗi.

### Kiểu Java không chứng minh khả năng lưu trữ

Có thể introspect `Map<UUID, Product>` không có nghĩa mọi store tự lưu được map đó với key UUID theo cùng biểu diễn. Có metadata cho một collection lồng nhau không có nghĩa mọi module ánh xạ trực tiếp nó thành cùng cấu trúc lưu trữ.

Cần tách các câu hỏi:

1. Java declaration mô tả cấu trúc kiểu nào?
2. Mapping metadata của module nhận diện các thuộc tính ra sao?
3. Converter có hỗ trợ chuyển đổi các giá trị đó không?
4. Store biểu diễn key, value, collection và quan hệ theo cách nào?

`TypeInformation` chủ yếu giải quyết câu hỏi đầu và hỗ trợ hạ tầng ở các bước sau. Nó không tự tạo converter, schema, join hoặc query.

Một POJO được introspect thành công cũng chưa phải entity đã được module đăng ký. TypeInformation của DTO và mapping metadata của một entity có mục đích khác nhau.

## 11. Thiết kế tiện ích đọc kiểu với hợp đồng rõ ràng

Giả sử một thành phần chỉ chấp nhận collection có kiểu phần tử cụ thể hơn Object. Có thể thể hiện yêu cầu đó như sau:

```java
import java.util.Objects;

import org.springframework.data.util.TypeInformation;

public final class CollectionTypes {

    private CollectionTypes() {
    }

    public static TypeInformation<?> requireSpecificElement(
            TypeInformation<?> type) {

        Objects.requireNonNull(type, "Thiếu thông tin kiểu");

        if (type.isMap() || !type.isCollectionLike()) {
            throw new IllegalArgumentException(
                "Yêu cầu collection hoặc array trong phạm vi được hỗ trợ"
            );
        }

        TypeInformation<?> component = type.getComponentType();

        if (component == null || component.getType().equals(Object.class)) {
            throw new IllegalStateException(
                "Cần kiểu phần tử cụ thể hơn Object"
            );
        }

        return component;
    }
}
```

Đây là chính sách của tiện ích, không phải quy tắc rằng `List<Object>` luôn là một khai báo Java sai. Một thành phần khác có thể cho phép Object hoặc giữ nguyên trạng thái chưa rõ để xử lý về sau.

Cách dùng:

```java
TypeInformation<?> productType = CollectionTypes.requireSpecificElement(
    catalogType.getRequiredProperty("products")
);
```

Tiện ích không khẳng định mọi value thật đều là Product, không validation dữ liệu và không đi qua toàn bộ collection lồng nhau. Nó chỉ kiểm tra một mức kiểu theo hợp đồng đã công bố.

### Khi xây một cây kiểu tổng quát

Nếu muốn duyệt đệ quy, cần giữ lại cả cấu trúc trung gian và xử lý chu kỳ. Một domain type có thể tham chiếu chính nó hoặc tham chiếu qua nhiều lớp khác rồi quay lại.

Cũng cần tránh đánh dấu đã thăm chỉ bằng raw class khi bài toán phải phân biệt `List<Product>` với `List<String>`. Hai cấu trúc có cùng raw class nhưng ngữ cảnh generic khác nhau. Khóa theo dõi nên phản ánh đủ thông tin kiểu mà công cụ cần bảo toàn, đồng thời có giới hạn độ sâu phù hợp.

Không làm phẳng map bằng cách chỉ theo value nếu mục tiêu là mô tả schema hoặc converter cho cả key lẫn value.

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Mọi List đều bị coi là cùng kiểu | Chỉ giữ getType hoặc Class | Giữ TypeInformation của thuộc tính đã phân giải |
| Map value bị nhận thành String | Dùng component type của Map<String, Product> | Dùng getMapValueType cho value |
| Map lồng List bị coi là Product ngay lập tức | Tưởng getActualType làm phẳng toàn bộ cấu trúc | Đi từng mức map value rồi collection element |
| Generic T vẫn không cụ thể | Tạo metadata từ raw lớp cha | Dùng ngữ cảnh lớp con hoặc nguồn khai báo có thông tin generic |
| Collection rỗng bị coi là không có kiểu | Suy kiểu từ dữ liệu runtime | Đọc khai báo qua metadata thay vì lấy phần tử đầu |
| Raw List được ép thành List<Product> | Coi Object hoặc thông tin thiếu như một kiểu miền đã biết | Công bố chính sách xử lý kiểu chưa rõ, tránh cast để che vấn đề |
| Lớp con Map không có hai type argument trực tiếp | Giả định tham số của lớp con đồng nhất với Map | Dùng API key/value và thông tin supertype |
| Property alias của store không tìm thấy | Dùng tên vật lý thay tên thuộc tính Java | Phân biệt TypeInformation với metadata tên trường lưu trữ |
| Introspection thành công nhưng converter thất bại | Đồng nhất cấu trúc kiểu với khả năng mapping | Kiểm tra conversion và quy tắc store riêng |
| Duyệt cây kiểu bị lặp vô hạn | Không xử lý tham chiếu đệ quy | Theo dõi kiểu đã xét và giới hạn phạm vi duyệt |

Không bắt mọi lỗi phân giải kiểu rồi tự trả Product.class. Một lỗi giả định cần được giữ rõ thay vì biến thành metadata có vẻ hợp lệ nhưng dẫn converter hoặc truy vấn đi sai hướng.

## 13. Tự thực hành đối chiếu kết quả

Dùng các mô hình ở trên để lần lượt đối chiếu:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Product scalar | Raw type và actual type đều biểu đạt Product |
| List<Product> và Set<String> | Phân biệt raw collection với component type |
| Product array | Component được đọc từ cấu trúc array |
| Map<String, Product> | Component là key; map value và actual type là Product |
| Map<String, List<Product>> | Giữ được ba mức Map, List và Product |
| List<List<Product>> | Một lần lấy actual type chưa đi tới Product cuối cùng |
| ProductEnvelope extends Envelope<Product> | Type variable được phân giải trong ngữ cảnh lớp con |
| Raw Envelope hoặc raw List | Không tự khôi phục generic cụ thể chưa được cung cấp |
| ProductIndex kế thừa Map đã cố định generic | Key/value được hiểu qua quan hệ kế thừa |
| Thuộc tính có wildcard | Không nhầm bound với runtime class chính xác của mọi phần tử |
| POJO không có annotation store | Có thể đọc kiểu Java nhưng chưa suy ra khả năng persistence |

Dùng TypeInformation hiệu quả là giữ được ngữ cảnh generic qua từng bước, phân biệt rõ collection element với map key/value và biết khi nào thông tin không đủ. Sau bước phân giải kiểu, mapping và converter của module mới quyết định cách cấu trúc Java đó được lưu, đọc và truy vấn trên kho dữ liệu thực tế.