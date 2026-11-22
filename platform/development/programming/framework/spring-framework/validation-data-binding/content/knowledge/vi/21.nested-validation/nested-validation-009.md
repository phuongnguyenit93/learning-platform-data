# Đồ thị có vòng lặp và phạm vi duyệt kiểm tra trong Jakarta Bean Validation

## 1. Tình huống thực tế: object graph không phải lúc nào cũng là cây

Các đối tượng trong ứng dụng Spring thường liên hệ với nhau theo nhiều chiều. `Order` tham chiếu `Customer`; `Customer` có danh sách `Order`; một nhân viên có `manager` nhưng manager lại có danh sách `reports` trỏ ngược. Hai field `billingAddress` và `shippingAddress` cũng có thể tham chiếu **đúng cùng một instance**. Các quan hệ đó tạo thành **đồ thị đối tượng** (*object graph*), đôi khi có chu trình.

Jakarta Bean Validation sử dụng `@Valid` để **cascade** kiểm tra từ bean gốc sang các bean được tham chiếu. Nhiều người lo ngại vòng lặp kiểu `A → B → A` sẽ gây stack overflow, hoặc nghĩ engine sẽ đánh dấu toàn bộ instance đã gặp rồi không bao giờ kiểm tra lại. Cả hai cách hiểu đều chưa chính xác:

- Provider chuẩn phải **chặn chu trình trên navigation path hiện tại** để cascade kết thúc.
- Cùng một instance có thể được **đi tới qua các nhánh khác nhau**; những nhánh ấy có thể tạo ra các lỗi mang **property path** khác nhau.
- Phạm vi engine đi sâu đến đâu còn phụ thuộc `@Valid`, `null`, constraint groups, container value extractors và `TraversableResolver`.

Mục tiêu bài học: hiểu quy tắc duyệt, dự đoán lỗi của đồ thị có vòng lặp hoặc object dùng chung, xây Java 17 demo và biết điều chỉnh phạm vi kiểm tra trong Spring MVC/JPA.

| Thuật ngữ | Nghĩa |
| --- | --- |
| **Root bean** | Object truyền trực tiếp vào `validator.validate(root)` |
| **Association** | Field/getter/reference, ví dụ `order.customer` |
| **Cascaded validation** | Đi từ object cha sang con qua quan hệ được đánh dấu `@Valid` |
| **Navigation path** | Một chuỗi các quan hệ `@Valid` từ root đến instance đang xét |
| **Constraint violation** | Kết quả lỗi của một constraint; có `propertyPath`, message, root/leaf bean |
| **Property path** | Vị trí logic dẫn tới lỗi, ví dụ `customer.address.street` |
| **Validation group** | Tập các constraint sẽ được chạy (`Default`, `Create`, `Publish`...) |

## 2. `@Valid` định nghĩa những cạnh được duyệt

Ví dụ Java minh họa:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

class Employee {
    @NotBlank
    String name;

    @Valid
    Employee manager;
}
```

Đoạn này dùng để giải thích field, chưa phải file thực thi đầy đủ. Khi gọi:

```java
Set<ConstraintViolation<Employee>> errors =
        validator.validate(employee);
```

provider kiểm tra constraint `name` của chính `employee`. Nếu `manager` không null, nó đi sang manager theo `@Valid`; nếu manager tiếp tục có manager được đánh dấu `@Valid`, validation có thể tiếp tục.

**Quy tắc ranh giới:**

1. Root được kiểm tra khi gọi `validate(root)`; **không cần annotation `@Valid` trên biến root**.
2. `@Valid` yêu cầu đi sâu qua reference/association được khai báo, không phải “kiểm tra mọi object reachable từ Java heap”.
3. Một field tham chiếu child nhưng **thiếu `@Valid`** không tự khiến các constraint của child chạy.
4. `@Valid` bỏ qua **tham chiếu null**; muốn cấm null, đặt thêm `@NotNull`.
5. `@Valid` có thể áp dụng với collection, array và các **type argument** `List<@Valid Child>`, `Map<K,@Valid Child>` nếu có value extractor phù hợp.
6. Constraints được chọn theo **group validation** đang áp dụng; một constraint không thuộc nhóm được chạy sẽ không sinh lỗi chỉ vì có `@Valid`.
7. Khi cascade tới subclass thực tế, provider dùng metadata constraint của kiểu object tương ứng.

Ví dụ ranh giới:

```java
class Department {
    @Valid Employee lead; // Kiểm tra bên trong lead

    Employee reviewer;    // Không tự đi sâu vào reviewer
}
```

Nếu `reviewer.name=""` còn `lead.name="Mai"`, lệnh `validator.validate(department)` sẽ không sinh lỗi của `reviewer` do field ấy thiếu `@Valid`. Để kiểm tra reviewer's fields, cần khai báo cascade ở **cạnh phù hợp**.

## 3. Vì sao vòng lặp `A → B → A` không chạy vô hạn?

Xét đồ thị:

```text
        root: A (name = "Alice")
                |
            @Valid next
                |
                v
             B (name = "")
                |
            @Valid next
                |
                v
             A (cùng instance root)
```

Đường duyệt từ A có các bước:

1. Kiểm tra constraint trên A.
2. Đi qua `A.next` tới B.
3. Kiểm tra constraint của B (ví dụ `@NotBlank` trên `name` phát hiện chuỗi rỗng).
4. Dự định cascade qua `B.next` trở lại **chính instance A**.
5. Vì A đã có trong **navigation path của nhánh này**, provider **bỏ qua thao tác cascade quay về A**.

Quy tắc được nêu rõ trong Jakarta Bean Validation 3.0, mục *Object graph validation*: provider phải bỏ qua cascade đến một instance **đã được validate trong đường duyệt hiện tại**, tránh vòng lặp vô hạn. Điều này vẫn cho phép engine kiểm tra các constraint của B trước khi gặp cạnh quay lại.

Đừng hiểu nhầm rằng Spring cần cấu hình một flag đặc biệt để chặn đệ quy: quy tắc tránh chu trình thuộc **đặc tả Jakarta Validation**, được các provider hợp lệ phải tuân theo. `fail-fast` của Hibernate Validator là một cơ chế riêng nhằm dừng sau lỗi đầu tiên, không phải công cụ bắt buộc để chống vòng lặp object graph.

### Identity quan trọng hơn `equals()`

Hai instance khác nhau nhưng có `id` giống nhau hoặc `equals()` trả `true` **không phải cùng một instance**. Quy tắc chu trình ở đây nói tới **object identity**, không phải bằng nhau về nội dung. Khi xây mô hình JPA, một entity proxy và một entity instance khác cùng khóa database có thể là hai object khác nhau; không suy luận cơ chế cắt vòng lặp chỉ từ `id`.

## 4. Tại sao object dùng chung có thể sinh nhiều lỗi?

Đồ thị sau **không có chu trình trong từng nhánh**:

```text
                 Root
                /    \
           @Valid    @Valid
             left    right
               \      /
                Shared
            (name = "")
```

Giả sử `Root.left == Root.right` (cùng instance `Shared`), và `Shared.name` vi phạm `@NotBlank`.

Các navigation paths khác nhau:

```text
Root → left  → Shared
Root → right → Shared
```

Mỗi path có thể tạo một `ConstraintViolation` với đường thuộc tính khác:

```text
left.name
right.name
```

Cả hai cùng liên quan một object nhưng vẫn là **hai vị trí lỗi trong mô hình dữ liệu từ root**. Nếu chỉ đánh dấu “đã thấy Shared” bằng một visited-set *toàn cục* rồi bỏ qua nhánh thứ hai, ta có thể làm mất path cần báo cho người dùng.

Đặc tả không bắt buộc provider thực thi lại cùng constraint trong mọi trường hợp: implementation có thể tối ưu, **miễn trả tập violations đúng**. Điều không được mất là thông tin các path lỗi mà contract yêu cầu.

| Tình huống | Kết quả nên hiểu |
| --- | --- |
| `A.next = B`, `B.next = A` | Cắt cạnh quay lại instance đã có **trên nhánh hiện tại** |
| `Root.left = X`, `Root.right = X` | Hai nhánh hợp lệ; có thể có `left.*` và `right.*` |
| Hai child có cùng giá trị nhưng là hai instance | Không tự coi chúng là một node |
| `child = null` chỉ có `@Valid` | Không cascade, không tự báo lỗi null |
| `@NotNull @Valid child = null` | `@NotNull` báo lỗi, `@Valid` không đi sâu |
| Cạnh thiếu `@Valid` | Không đi qua cạnh đó để kiểm tra child |

**Không được dùng `ConstraintViolation.getLeafBean()` làm khóa duy nhất** nếu muốn khử thông báo trùng trong UI: hai violations có thể cùng leaf bean nhưng khác `propertyPath`. Nếu cần tối ưu hiển thị, hãy quyết định theo path và mã lỗi, không tự bỏ dữ liệu tùy tiện.

## 5. Chu trình khi có List, mảng, Map và các nhánh lồng nhau

Không chỉ reference trực tiếp, các container cũng có thể giữ object tham chiếu ngược:

```java
class Team {
    java.util.List<@Valid Member> members;
}

class Member {
    @Valid Team team;
}
```

Đây là các lớp minh họa rút gọn; cần import `jakarta.validation.Valid` và các phần model còn lại khi dùng thực tế.

Với `Team.members[0].team` trỏ về đúng instance `Team` ban đầu, provider đi theo nhánh `Team → members[0] → Member` rồi cắt cạnh quay về `Team` theo quy tắc chống chu trình.

Nếu cùng một instance `Member` xuất hiện ở hai vị trí trong `List`, mỗi index có một navigation path riêng. Với Map, hai key khác nhau cùng trỏ tới một value object cũng tạo hai path.

```java
class ContainerRequest {
    java.util.List<@Valid Member> members;

    java.util.Map<String, @Valid Member> byDepartment;
}
```

Bảng minh họa:

| Cấu trúc | Vị trí có thể ghi lỗi |
| --- | --- |
| `List<@Valid Member>` | `members[0].name`, `members[1].name` |
| `Map<String,@Valid Member>` | `byDepartment[sales].name`, `byDepartment[tech].name` |
| `Map<String,List<@Valid Member>>` | Một nhánh qua Map value, tiếp qua List element |
| `@Valid Member[]` | Một nhánh cho từng object trong mảng |
| `Map<@Valid Key,@Valid Value>` | Cascade ở **key** và **value** được khai báo riêng |

Các chuỗi trên là cách mô tả ý nghĩa, không cam kết `toString()` của mọi Jakarta provider giống hệt nhau. Với Map, cách viết cũ `@Valid Map<K,V>` thường cascade vào **value**, không tự cascade key. Khi dùng type arguments, hãy đặt `@Valid` đúng vị trí; tránh đặt cả container và type argument cùng lúc chỉ để phòng hờ, vì có thể dẫn tới khai báo cascade trùng.

### Container constraints khác cascade

- `@NotEmpty List<@Valid Child>` yêu cầu danh sách không null/rỗng và cascade vào child **không null**, nhưng không cấm một phần tử null.
- `List<@NotNull @Valid Child>` vừa cấm phần tử null vừa cascade vào phần tử tồn tại.
- `Map<@NotBlank String, @NotNull @Valid Child>` kiểm tra **key** không trống, **value** không null và các constraints bên trong value.
- Với generic wrapper tùy chỉnh, có thể cần đăng ký `ValueExtractor` để provider biết cách lấy phần tử; `@Valid` không tự biến một wrapper bất kỳ thành container được hỗ trợ.

### Đọc đường dẫn có index và key

`ConstraintViolation.getPropertyPath()` trả `jakarta.validation.Path`, là iterable của `Path.Node`. Một node có thể chứa metadata của phần tử container:

```java
for (jakarta.validation.Path.Node node : violation.getPropertyPath()) {
    if (node.isInIterable()) {
        Integer index = node.getIndex();
        Object key = node.getKey();
        // index/key có thể null tùy container/node.
    }
}
```

Đây là snippet giả định biến `violation` tồn tại. Với List/array, index thường hữu ích; với Map, key thường hữu ích. Nếu response REST cần chỉ ra vị trí lỗi, hãy chuyển **structured path nodes** thành format API do bạn kiểm soát. Không nên phân tích string path bằng regex rồi coi là chuẩn giao tiếp bất biến.

## 6. Java 17 chạy độc lập: quan sát đệ quy và phạm vi duyệt

Chương trình dùng Hibernate Validator 8 làm provider Jakarta Validation. Ta cố tình kiểm tra sáu trường hợp:

- Cycle `A → B → A`.
- Object dùng chung ở hai field.
- Thiếu `@Valid` ở một tầng trung gian.
- Cùng instance ở hai vị trí List.
- Cùng instance ở hai key Map.
- `validateProperty(...)` chỉ xét property, không cascade qua `@Valid`.

Dự án Gradle:

```text
graph-cycle-validation/
├── settings.gradle
├── build.gradle
└── src/main/java/GraphCycleDemo.java
```

**`settings.gradle`**:

```groovy
rootProject.name = 'graph-cycle-validation'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'GraphCycleDemo'
}
```

`hibernate-validator` cung cấp provider; `expressly` cung cấp Jakarta EL implementation cho message interpolation. Trong dự án Spring Boot, ưu tiên `spring-boot-starter-validation` và BOM của Boot để chọn phiên bản tương thích.

**`src/main/java/GraphCycleDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

public class GraphCycleDemo {

    static final class Node {
        @NotBlank
        private final String name;

        @Valid
        private Node next;

        Node(String name) {
            this.name = name;
        }

        Node link(Node next) {
            this.next = next;
            return this;
        }
    }

    static final class Pair {
        @Valid private final Node left;
        @Valid private final Node right;

        Pair(Node left, Node right) {
            this.left = left;
            this.right = right;
        }
    }

    static final class ListBox {
        private final List<@Valid Node> nodes;

        ListBox(List<Node> nodes) {
            this.nodes = nodes;
        }
    }

    static final class MapBox {
        private final Map<String, @Valid Node> nodes;

        MapBox(Map<String, Node> nodes) {
            this.nodes = nodes;
        }
    }

    static final class Leaf {
        @NotBlank private final String name;

        Leaf(String name) {
            this.name = name;
        }
    }

    static final class Middle {
        private final Leaf leaf; // Thiếu @Valid.

        Middle(Leaf leaf) {
            this.leaf = leaf;
        }
    }

    static final class StopRoot {
        @Valid private final Middle middle;

        StopRoot(Middle middle) {
            this.middle = middle;
        }
    }

    static void show(String label, Object root, Validator validator) {
        Set<ConstraintViolation<Object>> issues = validator.validate(root);
        System.out.println(label + ": " + issues.size());
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Node a = new Node("Alice");
            Node b = new Node("");
            a.link(b);
            b.link(a); // Tạo chu trình: A -> B -> A.
            show("Cycle", a, validator);

            Node shared = new Node("");
            show("Shared", new Pair(shared, shared), validator);

            StopRoot stop = new StopRoot(new Middle(new Leaf("")));
            show("MissingCascade", stop, validator);

            show("List", new ListBox(List.of(shared, shared)), validator);

            show("Map", new MapBox(Map.of(
                    "billing", shared, "shipping", shared
            )), validator);

            System.out.println("Partial: "
                    + validator.validateProperty(a, "next").size());
        }
    }
}
```

Chạy với JDK 17+ và Gradle:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper: Linux/macOS `./gradlew run --quiet`; Windows `gradlew.bat run --quiet`.

**Standard output dự kiến:**

```text
Cycle: 1
Shared: 2
MissingCascade: 0
List: 2
Map: 2
Partial: 0
```

Giải thích:

1. `Cycle: 1`: A hợp lệ, B có `name=""` vi phạm `@NotBlank`; cạnh B quay lại A bị cắt trên nhánh hiện tại.
2. `Shared: 2`: `left` và `right` trỏ tới cùng `Node` có tên rỗng, nhưng là **hai đường lỗi** khác nhau.
3. `MissingCascade: 0`: `StopRoot` cascade vào `Middle`; `Middle.leaf` thiếu `@Valid`, nên không kiểm tra `Leaf.name`.
4. `List: 2`: cùng `shared` nằm ở index 0 và 1, mỗi vị trí có path lỗi riêng.
5. `Map: 2`: hai key của Map trỏ cùng `shared`; từng value được cascade.
6. `Partial: 0`: chỉ có `@Valid` trên `Node.next`, không có constraint trực tiếp trên field `next`; `validateProperty(a,"next")` **không cascade** vào B.

Demo chỉ in số lượng violations, không giả định thứ tự của `Set<ConstraintViolation<?>>`. Provider có thể ghi log khởi động qua stderr; stdout ở trên chỉ gồm các dòng `System.out.println`.

Muốn quan sát path, có thể thay đổi hàm `show` bằng snippet dưới đây (chạy **trong hàm**, không phải class độc lập):

```java
issues.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .forEach(System.out::println);
```

Khi kiểm tra `Shared`, bạn sẽ thấy các vị trí gần như `left.name` và `right.name`. Đường lỗi trong List/Map có thể có index/key và tên node khác nhau theo provider. Trong test quan trọng, nên kiểm tra cấu trúc node hoặc dùng provider đã được chọn cố định.

## 7. Các ranh giới duyệt khác cần hiểu

### 7.1. `validate()` khác `validateProperty()` và `validateValue()`

```java
validator.validate(order);
validator.validateProperty(order, "customer");
validator.validateValue(Order.class, "customer", customer);
```

Đây là các lời gọi minh họa có sẵn biến/type tương ứng. `validate(order)` đánh giá root và có thể cascade theo `@Valid`. `validateProperty` và `validateValue` chỉ đánh giá **constraint trực tiếp của thuộc tính**, **không tôn trọng `@Valid` để cascade vào bean con**. Vì vậy kết quả có thể rỗng dù một child bên dưới sai.

Theo Jakarta Validation API, tên property đưa vào `validateProperty`/`validateValue` là tên thuộc tính trực tiếp; không nên mặc định implementation portable sẽ chấp nhận một chuỗi path nhiều mức như `"customer.address.street"`.

### 7.2. Validation groups

Mặc định `validate(root)` kiểm tra nhóm `jakarta.validation.groups.Default`. Nếu gọi:

```java
validator.validate(order, PublishChecks.class);
```

mà constraint ở child chỉ được khai báo cho nhóm `Default`, việc không có lỗi thuộc nhóm `PublishChecks` **không phải do chống chu trình**. `@Valid` đưa validation sang child với nhóm đang dùng, trừ khi có cấu hình group conversion:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class Order {
    @Valid
    @ConvertGroup(from = Default.class, to = PublishChecks.class)
    Customer customer;
}
```

Đây là khai báo minh họa với nhóm `PublishChecks` và class `Customer` phải được định nghĩa thêm. Quy tắc chuyển nhóm chỉ tác động tại cạnh `@Valid` liên quan. Group sequence có thể khiến một nhóm sau không được chạy nếu nhóm trước có lỗi.

**Đừng nhầm vòng lặp object graph với vòng lặp group sequence**: chu trình nhóm không hợp lệ có thể gây `GroupDefinitionException`; không dùng quy tắc chống chu trình object để suy ra mọi cấu hình nhóm đều hợp lệ.

### 7.3. `TraversableResolver`

SPI `jakarta.validation.TraversableResolver` quyết định liệu property có thể được truy cập và cascade hay không:

- `isReachable(...)` kiểm soát tính có thể đọc để kiểm tra/cascade.
- `isCascadable(...)` kiểm soát việc đi qua quan hệ có `@Valid`, khi nó reachable.

Trong môi trường JPA, kiểm tra một quan hệ `LAZY` có thể liên quan đến nạp dữ liệu ngoài ý muốn. Provider và integration layer có thể dùng resolver để giới hạn truy cập. Do đó `@Valid` **không đảm bảo mọi association JPA đều được truy cập hoặc tự động fetch**; cần test cùng provider, transaction/persistence context và trạng thái loaded thực tế.

### 7.4. Root, null và nhóm ràng buộc trực tiếp

Một bean root được validate ngay khi gọi `validate(root)`, bất kể có quan hệ cascade nào. Các constraint trên root được kiểm tra nếu thuộc group đang chạy và property reachable. `@Valid` trên một quan hệ **không tự báo lỗi null**, cũng không buộc một List phải có phần tử. Dùng `@NotNull`, `@NotEmpty`, `@Size` đúng cấp để bổ sung yêu cầu đó.

## 8. Tích hợp Spring MVC: cần biết giới hạn nào?

Spring Framework 6+/Spring Boot 3+ dùng Jakarta namespace. Trong ứng dụng có provider Jakarta, Spring dùng `LocalValidatorFactoryBean` để tích hợp Bean Validation vào `DataBinder`/Spring MVC.

Ví dụ DTO và controller (các public record cần tệp Java cùng tên; đây là **snippets tích hợp**, không phải một project đầy đủ):

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public record AddressInput(@NotBlank String city) {}

public record CustomerInput(
        @NotBlank String name,
        @Valid AddressInput address
) {}
```

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {

    @PostMapping("/customers")
    public ResponseEntity<String> create(
            @Valid @RequestBody CustomerInput input) {
        return ResponseEntity.ok("accepted");
    }
}
```

Ví dụ body:

```json
{"name":"Mai","address":{"city":""}}
```

Khi Jackson deserialization thành công, `@Valid` trên `CustomerInput` và trên `address` cho phép provider kiểm tra `AddressInput.city`, phát hiện `@NotBlank` violation. Với handling mặc định, Spring MVC thường trả HTTP 400 nếu validation của command object không thành công. Phần trình bày lỗi cụ thể phụ thuộc exception handler và cấu hình.

**JSON không tự mang identity vòng lặp Java**: chu trình `A → B → A` thường xuất hiện sau khi ghép model/entity hoặc từ quan hệ JPA. Việc Bean Validation chống lặp **không sửa** vấn đề Jackson serialize object có cyclic reference. Nếu JSON serialization gặp vòng lặp, xử lý bằng DTO, identity/reference mapping hoặc cấu hình Jackson tương ứng.

Ngoài ra, endpoint `@RequestBody List<Item>` trực tiếp có ngữ nghĩa validation khác với một **wrapper command object** có `List<@Valid Item>`; đừng mặc định chỉ gắn `@Valid` lên collection argument sẽ tạo kết quả giống DTO wrapper trong mọi phiên bản MVC. Test chữ ký endpoint thực tế. Với `@ModelAttribute` và `BindingResult`, lỗi conversion/binding có thể khác lỗi constraint.

## 9. Hiệu năng và lựa chọn phạm vi kiểm tra

Chống vòng lặp không đồng nghĩa validation có chi phí cố định. Một graph nhiều nhánh có thể chứa một child dùng chung ở hàng trăm đường dẫn; provider vẫn phải bảo toàn tập violation paths đúng. Một số vấn đề:

- **Fan-out lớn:** nhiều container/quan hệ `@Valid` khiến số đường kiểm tra và số lỗi tăng.
- **Đồ thị sâu:** chiều sâu cascade lớn làm tăng chi phí đi qua quan hệ.
- **Constraint tốn kém:** regex nặng, truy vấn DB hoặc gọi mạng trong custom constraint là nguồn độ trễ; tránh đưa thao tác I/O lặp lại vào validator khi có thể.
- **JPA lazy loading:** việc truy cập relationship có thể kích hoạt nạp dữ liệu tùy resolver/provider. Không chủ động bật `FetchType.EAGER` chỉ để làm validation “đầy đủ”.
- **Một bean xuất hiện ở nhiều nhánh:** có thể được kiểm tra ở nhiều context/path; không dựa vào “mỗi instance chỉ được kiểm tra một lần”.
- **Hibernate Validator fail-fast:** là tùy chọn riêng provider, có thể dừng sau một violation và không cam kết lỗi nào thắng. Nó không thay thế phạm vi cascade có chủ đích.

Cách thiết kế phù hợp trong API thường là **validate một DTO có phạm vi dữ liệu cần cho use case** thay vì luôn cascade toàn bộ quan hệ domain entity/JPA. Đặt `@Valid` trên đúng cạnh cần kiểm tra, nhóm constraint có ý nghĩa, và test thực tế trên dữ liệu có quan hệ hai chiều/dùng chung.

Nếu ứng dụng dùng `ConstraintValidator` tùy chỉnh mà kiểm tra các field có vòng lặp bằng thuật toán tự viết, hãy tránh tự duyệt vô hạn trong **chính custom code**; quy tắc chống chu trình của provider áp dụng cho cơ chế cascade `@Valid` của nó, không thể bảo vệ mọi vòng lặp trong logic Java tùy chỉnh của bạn.

## 10. Ma trận test và lỗi thường gặp

### Bảng kiểm thử tối thiểu

| Kiểm thử | Mong đợi |
| --- | --- |
| A → B → A, B không hợp lệ | Phát hiện B, không chạy vô hạn |
| Root.left và Root.right trỏ cùng child sai | Hai vị trí lỗi khác nhau |
| Hai child khác instance nhưng `equals()` giống nhau | Không coi là chu trình theo object identity |
| `@Valid child = null` | Bỏ qua cascade; muốn cấm null dùng `@NotNull` |
| Một cạnh giữa chuỗi thiếu `@Valid` | Cascade dừng tại cạnh đó |
| Cùng child xuất hiện ở 2 index List | Có thể có hai path, mỗi index một vị trí |
| Cùng value dưới 2 key Map | Có thể có hai path theo key |
| `validateProperty(root,"child")` chỉ có `@Valid` | Không đi sâu vào child |
| Constraint child chỉ thuộc Publish, gọi Default | Constraint Publish không tự chạy |
| Cấu hình `@ConvertGroup` | Group chuyển ở đúng cạnh |
| Resolver không cho `isCascadable` | Không đi qua association đó |
| JPA lazy association chưa được load | Kiểm tra hành vi theo provider/resolver thật |
| Graph rộng và sâu | Đo thời gian, số lỗi và tải dữ liệu |

### Các hiểu lầm cần tránh

1. **“Mọi object chỉ validate một lần trong toàn bộ graph.”** Sai: cùng instance có thể sinh lỗi từ nhiều navigation paths.
2. **“Hai object có cùng `equals` là vòng lặp.”** Sai: quy tắc nói về cùng **instance**.
3. **“`@Valid` cấm null.”** Sai: thêm `@NotNull` nếu cần.
4. **“Reference luôn được cascade.”** Sai: phải đánh dấu quan hệ và được resolver cho phép.
5. **“`validateProperty` đi sâu theo `@Valid`.”** Sai: đây là partial validation, không cascade.
6. **“Khử lỗi theo instance là đủ.”** Không: dễ xóa mất vị trí đường dẫn.
7. **“Path string là chuẩn của mọi provider.”** Dùng `Path.Node` khi cần giao thức ổn định.
8. **“Fail-fast giúp tránh stack overflow của cascade.”** Nhà cung cấp Jakarta đã phải ngăn vòng lặp; fail-fast chỉ đổi chiến lược trả lỗi.
9. **“Nhóm nào cũng chạy miễn có `@Valid`.”** Không: groups/group sequence/conversion quyết định constraint áp dụng.
10. **“Spring MVC/Jackson có cùng vòng duyệt với Jakarta.”** Không: binding, serialization và validation là các pipeline khác nhau.
11. **“Đồ thị có chu trình thì phải xóa quan hệ hai chiều.”** Không nhất thiết; cắt chu trình đã có trong Jakarta, còn phạm vi DTO/use case là quyết định thiết kế.
12. **“Custom constraint có thể truy vấn DB trên mọi cạnh mà không sao.”** Đây là nguồn N+1/độ trễ; cần cân nhắc chi phí.

### Tự kiểm tra

1. Vì sao `A.next=B`, `B.next=A` không gây đệ quy vô hạn? **A đã nằm trên đường duyệt của nhánh quay lại, nên cascade đó bị bỏ qua.**
2. Vì sao cùng instance `Child` dưới `left` và `right` có thể cho hai lỗi? **Vì lỗi thuộc hai property paths khác nhau.**
3. Nếu `@Valid` tồn tại nhưng child không có lỗi, nên kiểm tra gì? **Null, vị trí `@Valid`, groups, type extractor, resolver, phạm vi API đã gọi.**
4. Nếu muốn chỉ kiểm tra một field và không đi vào object con, dùng gì? **`validateProperty` hoặc `validateValue` phù hợp, vốn không cascade.**
5. JSON có chu trình xuất ra được giải quyết bằng `@Valid` không? **Không**, cần giải pháp serialization/reference riêng.
6. Nếu root có hai association trỏ cùng child, việc dùng một global visited set trong custom validator có rủi ro gì? **Làm mất path lỗi của nhánh thứ hai.**

## 11. Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): mục Object graph validation (5.7.1), `validateProperty`/`validateValue`, groups, group conversion và traversable properties.
- [Jakarta Validation — `Validator` API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html): các overload `validate`, `validateProperty`, `validateValue`.
- [Jakarta Validation — `Path` API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Path.html): metadata path, index/key và các loại node.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): cascaded validation, container elements, fail-fast, `TraversableResolver`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): provider Jakarta và `LocalValidatorFactoryBean`.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, binding/validation và ngoại lệ HTTP.

**Điều quan trọng cần ghi nhớ:** Jakarta Validation **cắt cạnh quay về một instance đã nằm trên đường duyệt hiện tại** nhưng vẫn giữ các **đường lỗi khác nhau** đến một instance dùng chung. Phạm vi chạy thật phụ thuộc annotation, group, null, container extractor, resolver và API validation được gọi.
