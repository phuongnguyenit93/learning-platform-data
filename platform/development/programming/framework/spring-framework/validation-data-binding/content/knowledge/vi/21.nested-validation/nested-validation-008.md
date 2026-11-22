# Đường dẫn lỗi gồm tên trường, chỉ số và khóa trong Bean Validation

## 1. Mục tiêu: một lỗi không chỉ có thông báo

Khi validate DTO phức tạp trong Spring, một trường lỗi không nhất thiết nằm trực tiếp trên object gốc. Nó có thể ở bên trong một bean con, phần tử thứ ba của `List`, hoặc giá trị của một `Map` gắn với khóa `"home"`. Vì vậy, ngoài `message`, mỗi `ConstraintViolation<T>` của Jakarta Bean Validation còn có **đường dẫn lỗi** qua `getPropertyPath()`.

Ví dụ một đơn hàng có dữ liệu:

```text
OrderForm
├── customer
│   └── name = ""                          <- lỗi ở trường con
├── items
│   ├── [0] -> Item(sku = "A-01")
│   └── [1] -> Item(sku = "")               <- lỗi ở phần tử List số 1
└── addresses
    ├── ["home"] -> Address(zip = "12x")    <- lỗi trong Map tại khóa home
    └── ["work"] -> Address(zip = "12345")
```

Các đường dẫn thường thấy khi dùng Hibernate Validator:

```text
customer.name
items[1].sku
addresses[home].zip
```

Chúng có ba thành phần quan trọng:

- **Tên trường/property**: `customer`, `name`, `items`, `sku`, `addresses`, `zip`.
- **Chỉ số (index)**: `[1]` biểu thị phần tử của `List` ở vị trí 1, đếm từ 0.
- **Khóa (key)**: `[home]` biểu thị giá trị trong `Map` tương ứng với key `"home"`.

Tuy nhiên, các chuỗi trên là **biểu diễn dễ đọc**. Jakarta Validation không quy định mọi provider phải format `Path.toString()` cùng một cú pháp. API chuẩn thực sự là **`jakarta.validation.Path` với các `Path.Node`**, có metadata về tên, loại node, index và key.

Mục tiêu của bài:

1. Hiểu đường dẫn lỗi được tạo khi validate object lồng nhau qua `@Valid`.
2. Phân biệt `node.getName()`, `node.isInIterable()`, `node.getIndex()` và `node.getKey()`; hiểu tại sao `null` không luôn nghĩa là “không có key”.
3. Phân biệt path của constraint trên field bean với constraint đặt trên **phần tử container**, gồm `<list element>`, `<map key>` và `<map value>`.
4. Trích thông tin có cấu trúc để ánh xạ lỗi sang trường nhập trong Spring MVC/API, không chỉ thao tác chuỗi.
5. Chạy Java 17+ với Hibernate Validator và đối chiếu nested `ConstraintViolation` với `FieldError` của Spring.
6. Kiểm thử path ổn định mà không nhầm Bean Validation, data binding và JSON serialization.

## 2. `getPropertyPath()` trả về `Path`, không chỉ `String`

Với `jakarta.validation.ConstraintViolation<T>`:

```java
Path path = violation.getPropertyPath();
String readable = path.toString();
```

Đoạn này là **trích đoạn** trong hàm có `violation`; cần import `jakarta.validation.Path`. `Path` triển khai `Iterable<Path.Node>` nên có thể duyệt tuần tự các node.

API trung tâm:

```java
for (Path.Node node : path) {
    String name = node.getName();
    ElementKind kind = node.getKind();
    boolean inIterable = node.isInIterable();
    Integer index = node.getIndex();
    Object key = node.getKey();
}
```

Cần import thêm `jakarta.validation.ElementKind`. Mỗi node mô tả một bước trên đường đi từ đối tượng được validate đến vị trí vi phạm:

| Method của `Path.Node` | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `getName()` | Tên property/method/parameter hoặc tên node container do value extractor quy định | Có thể là `null` với node bean |
| `getKind()` | Loại node, chẳng hạn `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT` | Cùng tên nhưng loại node khác thì ý nghĩa khác |
| `isInIterable()` | Node có nằm trong một container như `List`, array, `Iterable`, `Map`? | Có thể `true` ngay cả khi cả index và key đều `null` |
| `getIndex()` | Chỉ số `Integer` nếu node nằm trong cấu trúc có index | `null` đối với Map, Set hoặc node không có vị trí số |
| `getKey()` | Khóa `Object` nếu node nằm trong container định vị bằng key | Không nhất thiết là `String`; có thể `Enum`, `Integer` hoặc `null` |
| `toString()` | Biểu diễn node/path dễ đọc | Không phải hợp đồng parse/serialize ổn định |

`Path.Node` còn có `as(Class<...>)` để chuyển sang interface node cụ thể khi `getKind()` tương ứng; với `Path.ContainerElementNode` có thể đọc `getContainerClass()` và `getTypeArgumentIndex()`.

**Quy tắc quan trọng nhất:** dùng `Path` để phân tích cấu trúc; dùng `path.toString()` cho hiển thị/log khi phù hợp, **không** dùng nó như định dạng máy bắt buộc hoặc thay thế JSON Pointer.

## 3. Tên trường: đường dẫn trong bean lồng nhau

Giả sử model có:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}

public class Customer {
    @NotBlank(message = "Customer name required")
    private String name;
}
```

Đoạn code này chỉ minh họa; cần import `jakarta.validation.Valid` và `jakarta.validation.constraints.NotBlank`, bổ sung constructor/getter/setter theo ứng dụng. Khi gọi `validator.validate(order)` và `customer.name = ""`, path thường là:

```text
customer.name
```

Hai `Path.Node` chính là:

```text
node 0: kind=PROPERTY, name=customer, inIterable=false
node 1: kind=PROPERTY, name=name,     inIterable=false
```

`customer` là property của root, `name` là property của child. Path tính **từ root được validate**. Nếu chỉ gọi `validator.validate(customer)` thì path trở thành `name` vì root bây giờ là `Customer`.

Để vi phạm ở `Customer.name` xuất hiện khi validate `OrderForm`, property `customer` phải có `@Valid` để cascade. `@NotBlank` bên trong child tự nó **không** buộc validator đi qua một tham chiếu chưa được gắn `@Valid`.

Nếu một child tiếp tục chứa `@Valid Address address` và `Address.zip` sai, path có thể là `customer.address.zip`: mỗi cạnh cascade thêm ngữ cảnh path.

### 3.1. Lỗi cấp class không nhất thiết có tên field

Constraint gắn ở **cấp class** kiểm tra quan hệ giữa nhiều property, ví dụ “ngày kết thúc phải sau ngày bắt đầu”. Nếu được validate ở root, path mặc định có thể là chuỗi rỗng và node `BEAN`. Nếu bean đó là child `customer`, lỗi class-level có thể gắn với đường dẫn bean con chứ không phải `customer.someField`.

Custom `ConstraintValidator` có thể dùng `ConstraintValidatorContext` và `.addPropertyNode("end")` để gắn lỗi vào một property cụ thể. Khi đó đường dẫn thay đổi theo cách builder được dùng. Đừng mặc định mọi violation có leaf `PROPERTY` tên khác `null`.

## 4. Chỉ số: lỗi ở phần tử `List` hoặc array

Model chứa danh sách các object con:

```java
public class OrderForm {
    private List<@Valid Item> items;
}

public class Item {
    @NotBlank
    private String sku;
}
```

Các đoạn trên là mã cấu trúc minh họa; cần `java.util.List`, `jakarta.validation.Valid` và `NotBlank`. Bean Validation 2.0+/Jakarta Validation 3.0 hỗ trợ annotation **ở type argument** để cascade vào từng element.

Nếu `items` có hai phần tử, phần tử đầu hợp lệ và `items.get(1).sku = ""`, Hibernate Validator thường biểu diễn:

```text
items[1].sku
```

Đường dẫn chứa index = 1 của element không hợp lệ, tính từ 0, **không phải** thứ tự 1-based mà người dùng nhìn thấy ở UI. Theo cơ chế cascaded validation, node `PROPERTY` mang tên `sku` có thể ghi nhận:

```text
node: name=sku
kind=PROPERTY
isInIterable=true
getIndex()=1
getKey()=null
```

Điều đáng chú ý: index **không nhất thiết gắn vào node có tên `items`**. Chuẩn mô tả context của container trên node theo sau quan hệ được duyệt; hãy kiểm tra toàn bộ `Path.Node` thay vì chỉ lấy node đầu tiên.

### 4.1. Constraint trên **phần tử String** khác với constraint bên trong bean

So sánh:

```java
private List<@Valid Item> items;
private List<@NotBlank String> tags;
```

- `@Valid` đi vào object `Item` để kiểm tra `Item.sku`. Path có thể là `items[1].sku`.
- `@NotBlank` trên **phần tử container** kiểm tra trực tiếp từng String. Khi `tags.get(0) = ""`, Hibernate Validator có thể trả:

```text
tags[0].<list element>
```

Ở trường hợp thứ hai, leaf node có thể là `CONTAINER_ELEMENT`, tên `<list element>`, `index = 0`; không có property `sku` vì lỗi nằm ngay trên element String.

`<list element>` là **tên node do value extractor** mặc định đưa ra, **không phải tên field Java**. Khi xây dựng API response, cần quyết định liệu sẽ ánh xạ lỗi về `tags[0]` hay giữ thông tin “vi phạm ở phần tử List” làm metadata.

### 4.2. `Iterable` và `Set` không nhất thiết có index

Một `Set<@NotBlank String>` hoặc `Iterable` không cung cấp địa chỉ phần tử theo index như `List`. Provider có thể đặt `isInIterable() == true` nhưng `getIndex() == null` và `getKey() == null`; hiển thị có thể chứa `[]` hoặc một node phần tử container.

Không suy ra “phần tử thứ nhất” bằng vị trí của item trong vòng lặp trên `Set`: thứ tự `Set` không phải hợp đồng định vị ổn định. Nếu UI cần liên kết lỗi với một control, thường nên dùng danh sách có index ổn định hoặc ID nghiệp vụ do ứng dụng quản lý.

### 4.3. Khi index thay đổi

`items[2].sku` là vị trí trong object được validate **tại thời điểm validation**. Nếu UI thêm/xóa/sắp xếp dòng sau đó, index cũ có thể trỏ tới item khác. Vì vậy:
- Gắn lỗi với đúng snapshot dữ liệu/request.
- Không dùng index như ID bền vững của entity.
- Có thể gửi thêm mã ID dòng do ứng dụng quản lý nếu nghiệp vụ cần định danh ổn định; tránh sửa trực tiếp `Path` như một cấu trúc mutable.

## 5. Khóa: lỗi ở giá trị của `Map`

Giả sử địa chỉ giao hàng được lưu theo nhãn:

```java
public class OrderForm {
    private Map<String, @Valid Address> addresses;
}

public class Address {
    @NotBlank
    private String zip;
}
```

Mã này là cấu trúc minh họa; cần `java.util.Map`, `@Valid`, `@NotBlank`. Khi `addresses.get("home").zip = ""`, Hibernate Validator thường tạo path:

```text
addresses[home].zip
```

`home` là **key** trong Map, không phải số thứ tự. Leaf node là property `zip` của bean con, và có thể cung cấp:

```text
node: name=zip
kind=PROPERTY
isInIterable=true
getIndex()=null
getKey()="home"
```

Khác với List, `Map` định vị phần tử bằng key, không phải index. Dù UI hiển thị các entry theo thứ tự, `getIndex()` vẫn không phải cách truy cập chính xác tới Map value.

**`getKey()` trả về `Object`.** Nếu Map dùng `Map<Integer, Address>`, key có thể là số nguyên; nếu `Map<Enum, Address>`, key là enum. Việc in `String.valueOf(key)` có thể mất thông tin kiểu, bị trùng biểu diễn hoặc chứa ký tự đặc biệt. Với public API hãy định nghĩa quy tắc encode key cho từng kiểu Map mà ứng dụng hỗ trợ.

### 5.1. Lỗi ở Map value khác với lỗi ở Map key

Cần phân biệt ít nhất ba tình huống:

```java
private Map<String, @Valid Address> addresses;
private Map<@NotBlank String, @Positive Integer> quantities;
```

Đoạn thứ hai kiểm tra trực tiếp **key** và **value** của Map bằng container-element constraints.

| Tình huống | Kiểu lỗi | Đường dẫn Hibernate Validator thường thấy |
| --- | --- | --- |
| `addresses["home"].zip` trống | Constraint trên field của bean con được cascade | `addresses[home].zip` |
| `quantities["home"] = -1` | Constraint `@Positive` trên **Map value** | `quantities[home].<map value>` |
| `quantities[""] = 1` | Constraint `@NotBlank` trên **Map key** | Có thể chứa node `<map key>` và ký hiệu đối số kiểu `<K>` |
| `quantities[null] = 1` với `Map<@NotNull String, ...>` | Constraint trên **Map key null** | Key null; path vẫn có thể là `CONTAINER_ELEMENT` nằm trong Map |

`<map value>` và `<map key>` là **tên node của container element**, không phải property của object được Map chứa. Mẫu hiển thị thực tế phụ thuộc provider; ví dụ Hibernate Validator có thể sử dụng biểu diễn như `quantities[home].<map value>` hoặc dạng `quantities<K>[].<map key>` khi khóa null.

**Điểm tinh tế:** `getKey() == null` chưa chắc nghĩa là node không nằm trong Map. Bản thân một **Map key bằng null** cũng có thể là khóa vi phạm, trong khi `isInIterable() == true`. Vì vậy phải xem `isInIterable`, loại node, cấu trúc container và quy tắc của value extractor, không chỉ kiểm tra `key != null`.

### 5.2. Nested container: `Map<String, List<@Valid Item>>`

Một object graph có thể kết hợp nhiều cấp:

```java
private Map<String, List<@Valid Item>> itemsBySection;
```

Ví dụ `itemsBySection.get("summer").get(2).sku` vi phạm thì path mang **cả key `summer` lẫn index `2`**. Jakarta Validation mô tả từng bước bằng các node. Với nested container, provider có thể thêm node `CONTAINER_ELEMENT` như `<map value>` hoặc `<list element>` để thể hiện chặng đi qua container.

Không nên cố đoán chuỗi tuyệt đối ví dụ là `itemsBySection[summer][2].sku`; trong các implementation và các ngữ cảnh giá trị khác nhau có thể xuất hiện thêm node container. **Duyệt node** để thu được key và index theo đúng thứ tự, rồi mới ánh xạ sang tên trường công khai do ứng dụng định nghĩa.

## 6. Loại node quyết định cách hiểu path

`ElementKind` cho biết node đại diện cho gì. Các giá trị phổ biến:

| `ElementKind` | Khi gặp | `getName()` có thể là |
| --- | --- | --- |
| `PROPERTY` | Constraint trên field/getter hoặc chặng đi qua property | `customer`, `items`, `sku` |
| `CONTAINER_ELEMENT` | Constraint trên phần tử List/Map/Optional hoặc container lồng nhau | `<list element>`, `<map key>`, `<map value>` |
| `BEAN` | Constraint cấp class của một bean | `null` |
| `METHOD` | Method được validate theo executable validation | Tên method |
| `PARAMETER` | Tham số method/constructor | Tên do `ParameterNameProvider` cung cấp |
| `RETURN_VALUE` | Return value của method/constructor | `<return value>` |
| `CROSS_PARAMETER` | Constraint kiểm tra tổ hợp tham số | `<cross-parameter>` |
| `CONSTRUCTOR` | Constructor được validate | Tên constructor theo mô tả spec |

Bài này tập trung `PROPERTY`, `CONTAINER_ELEMENT` và `BEAN` trên DTO, nhưng có thể gặp `METHOD`/`PARAMETER` khi validate tham số service. Đường dẫn loại method có thể bắt đầu bằng method node, không phải field của form.

Khi `kind == ElementKind.CONTAINER_ELEMENT`, nếu cần metadata chính xác hơn, có thể:

```java
Path.ContainerElementNode element =
        node.as(Path.ContainerElementNode.class);
Class<?> containerType = element.getContainerClass();
Integer argumentPosition = element.getTypeArgumentIndex();
```

Đây là đoạn **minh họa bên trong vòng lặp node**; chỉ thực hiện `node.as(...)` sau khi xác nhận đúng kind. Trong Java generics, `List<E>` có type argument index `0`; `Map<K, V>` có index `0` cho key và `1` cho value. API metadata này đặc biệt hữu ích khi Map key và Map value đều có constraint, hoặc nested containers khiến path dễ nhầm.

## 7. Ví dụ Java 17+ chạy độc lập: tên trường, index và key

Ví dụ cố định **Hibernate Validator 8.0.2.Final** (provider Jakarta Bean Validation) và **Spring Framework 6.2.14** để quan sát path thực tế cùng việc chuyển sang `BindingResult`. Mã tránh dựa vào thứ tự của `Set<ConstraintViolation<?>>` bằng cách sort theo path.

Ba lỗi:
- `customer.name` trống → path chỉ có tên trường.
- `lines.get(0).sku` trống → path có index List `0`.
- `offers.get("primary").sku` trống → path có key Map `"primary"`.

### 7.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-property-paths</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Tạo `src/main/java/demo/PropertyPathDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Path;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class PropertyPathDemo {

    public static final class Customer {
        @NotBlank(message = "Name is required")
        private String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static final class Item {
        @NotBlank(message = "SKU is required")
        private String sku;

        public Item(String sku) {
            this.sku = sku;
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static final class Order {
        @Valid
        private Customer customer;

        private List<@Valid Item> lines;

        private Map<String, @Valid Item> offers;

        public Order(Customer customer,
                     List<Item> lines,
                     Map<String, Item> offers) {
            this.customer = customer;
            this.lines = lines;
            this.offers = offers;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }

        public List<Item> getLines() {
            return lines;
        }

        public void setLines(List<Item> lines) {
            this.lines = lines;
        }

        public Map<String, Item> getOffers() {
            return offers;
        }

        public void setOffers(Map<String, Item> offers) {
            this.offers = offers;
        }
    }

    private static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    private static Integer indexOf(Path path) {
        for (Path.Node node : path) {
            if (node.getIndex() != null) {
                return node.getIndex();
            }
        }
        return null;
    }

    private static Object keyOf(Path path) {
        for (Path.Node node : path) {
            if (node.getKey() != null) {
                return node.getKey();
            }
        }
        return null;
    }

    public static void main(String[] args) {
        Order invalid = new Order(
                new Customer(" "),
                List.of(new Item("")),
                Map.of("primary", new Item(" ")));

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            Set<ConstraintViolation<Order>> found =
                    validator.validate(invalid);

            List<ConstraintViolation<Order>> errors =
                    new ArrayList<>(found);
            errors.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(errors.size() == 3, "Expected exactly three errors");

            for (ConstraintViolation<Order> error : errors) {
                Path path = error.getPropertyPath();
                Integer index = indexOf(path);
                Object key = keyOf(path);
                System.out.println(
                        path
                        + " | index=" + (index == null ? "-" : index)
                        + " | key=" + (key == null ? "-" : key)
                        + " | message=" + error.getMessage());
            }
            System.out.println("violations=" + errors.size());

            // Spring chuyển các violations về FieldError.
            BeanPropertyBindingResult bindingResult =
                    new BeanPropertyBindingResult(invalid, "order");
            new SpringValidatorAdapter(validator)
                    .validate(invalid, bindingResult);

            boolean listFieldPresent =
                    bindingResult.getFieldError("lines[0].sku") != null;
            boolean mapFieldPresent =
                    bindingResult.getFieldError("offers[primary].sku") != null;

            require(bindingResult.getFieldErrorCount() == 3,
                    "Spring must have three field errors");
            require(listFieldPresent, "Missing list field error");
            require(mapFieldPresent, "Missing map field error");

            System.out.println(
                    "springFieldErrors=" + bindingResult.getFieldErrorCount());
            System.out.println("springListField=" + listFieldPresent);
            System.out.println("springMapField=" + mapFieldPresent);

            Order valid = new Order(
                    new Customer("Mai"),
                    List.of(new Item("SKU-001")),
                    Map.of("primary", new Item("SKU-002")));
            require(validator.validate(valid).isEmpty(),
                    "Expected no violations on valid order");
            System.out.println("validViolations=0");
            System.out.println("CHECKS: PASS");
        }
    }
}
```

Các kiểm tra path dùng `Path.Node` để lấy index/key **thay vì parse chuỗi path**. Riêng khi tìm `FieldError` trong Spring, ví dụ sử dụng tên field do Spring adapter xây dựng và do Hibernate Validator biểu diễn trong phiên bản được cố định. Cần kiểm thử trên cấu hình converter/binder thực tế của dự án.

### 7.3. Chạy chương trình

Dùng JDK 17+ và Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.PropertyPathDemo
```

Các dòng dự kiến do chương trình in, không tính thông tin log khởi động của thư viện:

```text
customer.name | index=- | key=- | message=Name is required
lines[0].sku | index=0 | key=- | message=SKU is required
offers[primary].sku | index=- | key=primary | message=SKU is required
violations=3
springFieldErrors=3
springListField=true
springMapField=true
validViolations=0
CHECKS: PASS
```

Cách đọc:
1. `customer.name` cho biết hai tên property, **không có** index hoặc key.
2. `lines[0].sku` có property `lines`, một phần tử tại index `0`, và property lỗi `sku`.
3. `offers[primary].sku` có property `offers`, entry tại key `"primary"`, và property lỗi `sku`.
4. Ba lỗi đều là `@NotBlank` chạy sau các cạnh `@Valid` thích hợp.
5. `SpringValidatorAdapter` chuyển cùng các Bean Validation violations thành `FieldError` để view/controller có thể tìm theo path.
6. Object hợp lệ không có violation. Kết quả được sort theo path trước khi in, nên thứ tự stdout ổn định theo ví dụ đã cấu hình.

**Giới hạn tính portable:** Cú pháp của chuỗi `Path.toString()` trong stdout phản ánh Hibernate Validator 8.x và đường đi ở ví dụ; Jakarta Validation API chuẩn khuyến nghị **duyệt node** nếu cần thao tác có cấu trúc. Những provider khác hoặc nested containers phức tạp có thể hiển thị khác. Khi nâng cấp implementation, chạy lại test.

## 8. Duyệt `Path.Node` chi tiết để xây dựng error location

Đoạn mã dưới đây minh họa cách lấy một **danh sách segment trung gian** từ `ConstraintViolation`; tùy hợp đồng API, có thể convert các segment đó sang DTO typed. Mã này là **method có thể đặt trong class Java** khi có `jakarta.validation.Path`, `java.util.List` và `java.util.ArrayList`:

```java
static List<String> describePath(Path path) {
    List<String> parts = new ArrayList<>();

    for (Path.Node node : path) {
        String type = node.getKind().name();
        String name = node.getName() == null
                ? "<bean>" : node.getName();

        String location = "kind=" + type + ",name=" + name;
        if (node.isInIterable()) {
            location += ",iterable=true";

            if (node.getIndex() != null) {
                location += ",index=" + node.getIndex();
            }
            if (node.getKey() != null) {
                location += ",key=" + node.getKey();
            }
        }
        parts.add(location);
    }
    return parts;
}
```

**Lưu ý về trích đoạn:**
- Đoạn này dùng `String.valueOf` ngầm thông qua nối chuỗi, chỉ thích hợp debug các key đã kiểm soát; public API phải encode có kiểm soát.
- Nếu cả `getIndex()` và `getKey()` bằng null mà `isInIterable()` vẫn `true`, metadata vẫn nói node **nằm trong iterable**, chẳng hạn `Set` hoặc entry Map với key null.
- Một node `CONTAINER_ELEMENT` với tên `<list element>` không được tự biến thành property tên `"list element"` trong object.
- Với dữ liệu rất lớn hoặc key có `toString()` phức tạp, đừng log toàn bộ path/key nếu chưa có giới hạn kích thước và chính sách ẩn dữ liệu.

### 8.1. Khi nào cần `as(Path.ContainerElementNode.class)`?

Khi lỗi là constraint trên phần tử generic như:

```java
private List<@NotBlank String> tags;
private Map<@NotBlank String, @Positive Integer> quantities;
```

đoạn dưới nằm trong một vòng duyệt `Path.Node`:

```java
if (node.getKind() == ElementKind.CONTAINER_ELEMENT) {
    Path.ContainerElementNode element =
            node.as(Path.ContainerElementNode.class);

    Class<?> containerClass = element.getContainerClass();
    Integer argumentIndex = element.getTypeArgumentIndex();
    // List<E>: argumentIndex thường 0
    // Map<K, V>: 0 cho key, 1 cho value.
}
```

Cần import `jakarta.validation.ElementKind`; type argument metadata giúp phân biệt khi path có nhiều segment container. Đây là thông tin mạnh hơn việc nhìn thấy dấu ngoặc vuông trong text.

### 8.2. Những trường hợp không thể “dịch” path thành field name một cách máy móc

- Constraint cấp class có thể có path rỗng hoặc `BEAN` leaf.
- Cross-parameter violation có node method và `<cross-parameter>`.
- Validation của return value có `<return value>`.
- Constraint trên Map **key** không phải property trong bean **value**.
- `Optional<@NotNull ...>` có thể được coi là container trong suốt và path hiển thị không chứa tên element.
- `List<@NotBlank String>` có thể tạo `<list element>` thay vì field path của object.
- Key chứa dấu chấm, dấu `]`, slash, quote hoặc Unicode làm cho việc `split(".")`/regex theo bracket không đáng tin.
- Một property tên `"items"` trong JSON có thể dùng một tên khác trong Java DTO vì `@JsonProperty`, naming strategy hoặc mapping thủ công.

Nếu public API cần location chính xác, hãy định nghĩa một **hợp đồng ánh xạ** từ các node sang field path client, với quy tắc escape/encode được kiểm thử.

## 9. Spring MVC: từ `ConstraintViolation` sang `BindingResult`

Trong Spring Framework, việc kết hợp `@Valid` và `BindingResult` thường trông như:

```java
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "orders/form";
    }
    return "orders/success";
}
```

Đây là **trích đoạn controller Spring Web MVC**, cần `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `ModelAttribute`, và `org.springframework.validation.BindingResult`.

Quan hệ hai tầng annotation:

```text
@Valid @ModelAttribute OrderForm -> yêu cầu kiểm tra root khi nhận request
    @Valid Customer customer    -> đi sâu từ root sang Customer
    List<@Valid Item> items     -> đi sâu vào mỗi Item trong List
    Map<String, @Valid Item>    -> đi sâu vào từng Item value trong Map
```

`@Valid` ở tham số controller khởi động validation trong flow MVC; `@Valid` trên field/type argument quyết định cascade tới child. Với lời gọi trực tiếp `Validator.validate(order)` của Jakarta Validation, root đã được validate bởi chính lời gọi, không cần annotation trên biến local.

Khi hạ tầng Spring MVC được cấu hình đúng, lỗi nested được đưa vào `BindingResult`:

```java
FieldError firstItemError =
        errors.getFieldError("items[1].sku");
FieldError homeZipError =
        errors.getFieldError("addresses[home].zip");
```

Đây là trích đoạn nằm sau khi đã có `BindingResult errors`; `FieldError` thuộc `org.springframework.validation.FieldError`. Các field path này **có thể** tương ứng với `ConstraintViolation.getPropertyPath().toString()`, nhưng không nên coi sự tương ứng là quy luật tuyệt đối cho mọi provider, container element hoặc lỗi binding.

### 9.1. Jakarta path và Spring field path khác nhau ở điểm nào?

| Jakarta Bean Validation | Spring validation/binding | Nhận xét |
| --- | --- | --- |
| `ConstraintViolation.getPropertyPath()` | `FieldError.getField()` | Jakarta trả `Path` có node metadata; Spring trả tên field `String` |
| `getInvalidValue()` | `FieldError.getRejectedValue()` | Giá trị lỗi có thể khác ở trường hợp raw input/type conversion |
| `getMessage()` | `FieldError.getDefaultMessage()` | Thường là message đã xử lý, có thể tiếp tục được resolve qua `MessageSource` |
| `getMessageTemplate()` | Không có getter tương ứng trực tiếp trên `FieldError` | Spring cung cấp error codes/arguments; không phải template Jakarta |
| Node index/key | Property access path của `BeanWrapper`/binder hoặc field path do adapter chuyển đổi | Cần kiểm thử khi nested List/Map và key đặc biệt |
| Violation cấp bean | `ObjectError` | Không nhất thiết ánh xạ thành `FieldError` |

Spring có thể tạo `FieldError` mà không có `ConstraintViolation`, ví dụ người dùng gửi `"abc"` cho field `Integer qty` và data binding tạo lỗi `typeMismatch`. Validation của Jakarta diễn ra trên object Java đã tạo được; nó không đồng nghĩa một parser chuỗi tùy ý.

### 9.2. Binding vào List/Map có thêm quy tắc riêng

Đường field mà Spring sử dụng trong form, ví dụ `items[1].quantity`, là đường truy cập property dựa trên `DataBinder`/`BeanWrapper`. Trước khi Bean Validation chạy, binder phải:
- Chuyển chuỗi input thành kiểu thuộc tính đích.
- Xác định phần tử List hoặc entry Map tương ứng.
- Có collection/map và đối tượng con phù hợp để có thể cập nhật field.

Tùy cấu hình, binder có thể tự tăng kích thước collection đến một giới hạn (`autoGrowCollectionLimit`), tự tạo nested path hoặc từ chối key/index không hợp lệ. **Đó là hành vi binding**, không phải nội dung của chuẩn Jakarta `Path`.

Từ góc độ an toàn, đừng cho phép client tùy ý gán mọi nested property của domain entity. Dùng DTO dành riêng cho input, giới hạn writable fields, độ sâu, collection size, converter và các trường nhạy cảm trước khi áp dụng validation.

### 9.3. Với `@RequestBody` JSON

JSON HTTP body được parse/deserialized (thường qua Jackson) trước khi validation. Nếu JSON không đọc được, lỗi có thể là `HttpMessageNotReadableException`, không có `ConstraintViolation`. Nếu deserialize xong mà `items[1].sku` trống, Bean Validation có thể tạo violation có index.

Bản thân `getPropertyPath().toString()` **không** phải JSON Pointer. Nếu API dùng JSON Pointer kiểu `/items/1/sku`, hãy chuyển có chủ đích từ path nodes và mapping Java↔JSON (ví dụ `@JsonProperty`, naming strategy). Dấu `~` và `/` trong JSON Pointer phải escape theo RFC 6901; key Map chứa dấu `/` không thể ghép trực tiếp vào JSON Pointer.

## 10. Thiết kế API response có lỗi theo field, index và key

Một response do **ứng dụng tự thiết kế** có thể như sau:

```json
{
  "errors": [
    {
      "location": {
        "property": "items",
        "index": 1,
        "childProperty": "sku"
      },
      "code": "SKU_REQUIRED",
      "message": "Mã sản phẩm không được để trống"
    },
    {
      "location": {
        "property": "addresses",
        "key": "home",
        "childProperty": "zip"
      },
      "code": "ZIP_INVALID",
      "message": "Mã bưu chính không hợp lệ"
    }
  ]
}
```

Đây **không phải** payload mặc định của Spring MVC hay Jakarta Validation. Ưu điểm của `location` có cấu trúc là phân biệt `index: 1` (Integer) và `key: "1"` (String), đồng thời tránh phải parse một chuỗi chứa nhiều bracket.

Nguyên tắc triển khai:

1. **Mã lỗi ổn định:** chọn `code` do domain/API quản lý, không dùng thông báo đã dịch làm ID.
2. **Kiểm soát tên field public:** Java property path không nhất thiết trùng tên field client.
3. **Giữ kiểu key/index:** index luôn là số, key giữ type hoặc encode theo schema API.
4. **Không lộ dữ liệu:** `getInvalidValue()` có thể chứa password/token/PII, không đưa vào response mặc định.
5. **Giới hạn độ dài/path depth:** path hoặc Map key do client ảnh hưởng có thể quá lớn; đặt giới hạn và kiểm thử.
6. **Đặt lỗi phù hợp:** class-level errors nên có `location` cấp object/`null`, không bịa tên field.
7. **Không dựng property access từ path thiếu kiểm tra:** tránh sử dụng input không đáng tin cậy để tự động đọc/ghi property nội bộ.

### 10.1. Key có dấu chấm hay ngoặc vuông

Ví dụ Map key là `"a.b"` hoặc `"main]backup"`. Một chuỗi path dễ đọc có thể trông như `addresses[a.b].zip` hoặc biểu diễn khác tùy provider. Nếu dùng `split("\\.")` để tách, dấu chấm trong **key** bị hiểu nhầm là ranh giới property.

Lời giải đúng là lấy `Path.Node.getKey()` khi có, rồi encode key theo quy tắc API. Với Map key là object tùy chỉnh, có thể cần một **key serializer** nhất quán; không mặc định `Object.toString()` an toàn hoặc duy nhất.

### 10.2. Liên kết lỗi với dòng trong UI động

Một form cho phép thêm/xóa dòng có thể đổi thứ tự List giữa hai request. Nếu server trả lỗi `items[2].sku` cho dữ liệu gửi lên ở thời điểm đó, UI nên hiển thị dựa trên **snapshot vừa submit**, không gắn index vào một item đã bị sắp xếp lại. Đối với form phức tạp, gửi kèm ID dòng do ứng dụng quản lý có thể giúp hiển thị chính xác, nhưng `Path.getIndex()` bản thân không tạo ra ID nghiệp vụ.

## 11. Kiểm thử path có cấu trúc và hành vi thật

| Case | Cấu hình/dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Field root | `@NotBlank String name` trống | Path có một node `PROPERTY` tên `name` |
| Field ở child | `@Valid Customer`, `customer.name` trống | Path gồm `customer` rồi `name` |
| Thiếu `@Valid` | Child sai nhưng parent không cascade | Không có violation child từ validate parent |
| `List<@Valid Item>` | Item ở index 0 sai | Có `isInIterable=true`, `getIndex()==0` trên node thích hợp |
| `List<@NotBlank String>` | Element ở index 1 trống | Có node `CONTAINER_ELEMENT` như `<list element>` |
| `Set<@NotBlank String>` | Một element sai | `isInIterable=true` dù index/key có thể null |
| `Map<String, @Valid Address>` | Value tại key `"home"` sai | `getKey()` tương ứng `"home"` |
| `Map<@NotBlank String, Integer>` | Key trống | Leaf có thể `<map key>`; không phải field của value |
| `Map<String, @Positive Integer>` | Value âm | Leaf có thể `<map value>` |
| Map với key null | Key null vi phạm `@NotNull` | Phân biệt `isInIterable=true` và `getKey()==null` |
| Nested Map→List | `Map<String,List<@Valid Item>>` | Có cả metadata key và index theo các node |
| Key chứa dấu chấm | `"a.b"` | Không tách path bằng dấu chấm thủ công |
| Key không phải String | `Map<Integer, Item>` | Không nhầm key số với index List |
| Class-level constraint | Hai field không nhất quán | Path có thể là node `BEAN`/không có leaf field |
| Method parameter | Constraint trên parameter | Path có node `METHOD`, `PARAMETER` và tên do cấu hình |
| Lỗi conversion | `"x"` bind vào `Integer` | Spring `typeMismatch`, không nhất thiết có Jakarta violation |
| JSON mapping | `@JsonProperty("items")` hoặc naming strategy | Path Java không mặc nhiên là JSON Pointer |
| UI sửa thứ tự | Form động thay đổi index | Index gắn với snapshot validation, không phải ID |
| Locale | Message tiếng Anh/Việt | Path metadata không phải message dịch |
| Nhạy cảm | Map key chứa token/PII | Không log trả raw key/invalid value tùy ý |

Để test **đúng cấu trúc** thay vì một chuỗi path cố định:

```java
boolean hasIndexZero = violations.stream()
        .anyMatch(v -> {
            for (Path.Node node : v.getPropertyPath()) {
                if (Integer.valueOf(0).equals(node.getIndex())) {
                    return true;
                }
            }
            return false;
        });
```

Đây là **trích đoạn trong test** với `violations` đã có và import `jakarta.validation.Path`. Nếu một object có nhiều collection, kiểm tra thêm chuỗi node `PROPERTY` (`items`), node `CONTAINER_ELEMENT`/leaf property, thay vì chỉ xác nhận tồn tại index `0` ở bất kỳ chỗ nào.

### 11.1. Kiểm tra path có cả key và index

Với cấu trúc `Map<String, List<@Valid Item>>`, đừng chỉ assert `Path.toString()` theo một mẫu suy đoán. Có thể:
- Duyệt từng `Path.Node` theo thứ tự.
- Ghi nhận `getKind()`, `getName()`, `isInIterable()`.
- Tìm key `"summer"` ở một node, index `2` ở node thích hợp tiếp theo.
- Kiểm tra leaf property `sku`.
- Dùng metadata `ContainerElementNode.getTypeArgumentIndex()` khi có nhiều level generic.

Nếu cần test integration cho framework cụ thể, bổ sung test riêng cho `FieldError.getField()` hoặc payload JSON client. Test portable (node metadata) và test giao diện (chuỗi hiển thị) có **mục đích khác nhau**.

## 12. Những lỗi phổ biến và cách sửa

**1. Coi `getPropertyPath()` luôn là `String`.** Nó trả `Path`. `toString()` giúp log, nhưng để biết index/key và loại container phải duyệt `Path.Node`.

**2. Lấy chỉ số từ regex `\\[(\\d+)\\]`.** Một Map key có thể là `"123"`, rất dễ bị hiểu nhầm là index 123. Dùng `getIndex()` và `getKey()` để giữ ngữ nghĩa.

**3. Giả sử `getIndex() == null && getKey() == null` nghĩa là node không ở container.** Với Set, Iterable không index hoặc Map có key null, `isInIterable()` vẫn có thể `true`.

**4. Gắn index vào nhầm node.** Metadata về container có thể đặt trên node con (`sku`/`CONTAINER_ELEMENT`), không phải node property tên `items`; duyệt toàn bộ path.

**5. Tưởng `<map value>` là field Java.** Đó là tên node của value extractor. Trong response nên biểu diễn “Map value tại key X bị lỗi”, không tìm property literal `<map value>` trên DTO.

**6. Quên `@Valid` ở cạnh cha.** Không có cascade, validator khởi đầu ở root sẽ không duyệt tới child dù child có constraint. `@Valid` không tự tạo constraint và không tự bắt null; dùng `@NotNull` nếu tham chiếu bắt buộc.

**7. Tin rằng mọi lỗi Spring `FieldError` xuất phát từ Jakarta Validation.** `typeMismatch` có thể xuất hiện trước Bean Validation, đặc biệt khi List/Map chứa số hoặc nested DTO chưa bind được.

**8. Dùng `Set` nhưng kỳ vọng `items[0]`.** Set không có thứ tự index chuẩn, nên không thể hứa đường dẫn theo vị trí hiển thị. Cần dùng collection hoặc ID phù hợp yêu cầu UI.

**9. Ghép Map key vào JSON Pointer hoặc HTML input name mà không escape.** Key có thể chứa `/`, `~`, `.`, `]`, whitespace hoặc Unicode; phải áp dụng quy tắc serialize/escape cho giao thức đích.

**10. Dùng path nội bộ làm tài nguyên truy cập không cần kiểm soát.** Path và key có thể chịu ảnh hưởng input; không được dùng chúng như quyền đọc/ghi arbitrary property của domain object.

**11. Không kiểm tra instance gốc và validation group.** Validate trực tiếp child cho path khác validate từ parent. `@Validated` với group khác có thể thay đổi tập violation và những cạnh được cascade.

**12. Gắn validation message vào key/path rồi log cả giá trị nhạy cảm.** Đường Map có thể chứa email, token hoặc ID. Áp dụng masking, giới hạn kích thước và tách error code khỏi nội dung message.

**13. Trộn Jakarta và javax packages.** Spring Framework 6+ dùng hệ sinh thái `jakarta.validation.*`; với Spring Framework 5.x cũ thường là `javax.validation.*`. Chọn API/provider đồng nhất, không đổi một nửa namespace.

## 13. Quy trình áp dụng trong một endpoint Spring

1. **Xác định DTO** và nơi validation bắt đầu: `@Valid @ModelAttribute`, `@Valid @RequestBody` hay gọi `Validator.validate(...)` trực tiếp.
2. **Đánh dấu cascade** ở mỗi cạnh cần duyệt: `@Valid` trên bean con, `List<@Valid Item>` hoặc `Map<String, @Valid Item>`.
3. **Xác định required/nullable** độc lập bằng `@NotNull`, `@NotBlank`, `@NotEmpty` hoặc hợp đồng riêng.
4. **Kiểm tra data binding** cho index/key; giới hạn writable fields, collection auto-grow và converter.
5. **Truy xuất violation** bằng `getPropertyPath()` và các node; tránh parse `Path.toString()` như chuẩn bắt buộc.
6. **Ánh xạ ra public location**: field, List index, Map key, container-element kind; escape và giới hạn dữ liệu.
7. **Tách thông báo** (`getMessage()`), mã lỗi nghiệp vụ và metadata debug; không tiết lộ `getInvalidValue()` mặc định.
8. **Kiểm thử thực tế** cho nested property, List, Map, key có ký tự đặc biệt, Set/null, data conversion, JSON property naming và UI thay đổi thứ tự.
9. **Giữ ổn định response API** trong khi có thể thay provider Jakarta Validation hoặc nâng cấp Spring/Jackson.

## 14. Tài liệu chính thức

- Jakarta Bean Validation 3.0 Specification — mô hình `ConstraintViolation`, `Path` và `Node`, cascade/container element: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API 3.0 — `Path`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.html
- Jakarta Validation API 3.0 — `Path.Node`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.Node.html
- Jakarta Validation API 3.0 — `Path.ContainerElementNode`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.ContainerElementNode.html
- Jakarta Validation API 3.0 — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Hibernate Validator 8 — Reference Guide, nested and container element constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework 6.2 — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/FieldError.html
