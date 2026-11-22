# Record trong Java: từ preview Java 14 đến tính năng chính thức từ Java 16

## 1. Vì sao cần hiểu hành trình từ Java 14 đến Java 16?

`record` là cú pháp khai báo một **lớp dữ liệu** (*record class*) trong Java. Thay vì lặp lại các khai báo trường, constructor, phương thức truy cập và các phương thức so sánh, ta mô tả dữ liệu bằng các **record component** ngay trên phần đầu khai báo:

```java
public record Coordinate(int x, int y) {}
```

`Coordinate` ở ví dụ này là một **kiểu tham chiếu** giống lớp Java khác, nhưng có khuôn mẫu đặc biệt cho dữ liệu. `new Coordinate(2, 3)` tạo một đối tượng có hai component `x` và `y`. Từ mỗi component, trình biên dịch cung cấp trường `private final`, accessor công khai `x()`/`y()`, constructor chuẩn, `equals`, `hashCode` và `toString`.

Câu “record xuất hiện trong Java 14” **đúng về lịch sử**, nhưng khi viết phần mềm hiện nay cần ghi rõ: **Java 14 và Java 15 chỉ thử nghiệm (`preview`); từ Java 16, records là tính năng chính thức (`finalized / permanent`).** Vì vậy, ví dụ thực hành trong bài dùng cú pháp chuẩn của **Java 16+**, vẫn sử dụng được trên các JDK hiện đại, không yêu cầu cờ preview.

## 2. Ba mốc phát triển quan trọng

| Phiên bản | Tài liệu chuẩn hóa | Trạng thái record | Ý nghĩa đối với người học hiện nay |
| --- | --- | --- | --- |
| **Java 14 (2020)** | [JEP 359 — Records (Preview)](https://openjdk.org/jeps/359) | **Preview lần thứ nhất** | Giới thiệu khai báo record và cơ chế mang dữ liệu minh bạch; đây là **bối cảnh lịch sử**, chưa phải cam kết tính năng ổn định |
| **Java 15 (2020)** | [JEP 384 — Records (Second Preview)](https://openjdk.org/jeps/384) | **Preview lần thứ hai** | Tiếp thu phản hồi và bổ sung hỗ trợ **local record** khai báo bên trong phương thức |
| **Java 16 (2021)** | [JEP 395 — Records](https://openjdk.org/jeps/395) | **Chính thức, không còn preview** | Cú pháp record trở thành một phần ổn định của Java; các hạn chế về thành viên `static` trong inner class cũng được nới lỏng, bao gồm record lồng (record lồng mặc định là `static`) |

**Diễn giải đúng mốc phiên bản:**

1. **Java 14** là phiên bản đầu tiên để giới thiệu và lấy phản hồi về thiết kế `record`. Đừng hiểu “có từ Java 14” là “Java 14 là mốc ổn định để dùng record trong ứng dụng mới”.
2. **Java 15** vẫn là preview; một bổ sung đáng chú ý là **local record**, tức record được khai báo cục bộ trong thân phương thức để mô tả dữ liệu tạm phục vụ thuật toán.
3. **Java 16** là mốc nên nhớ khi đọc mã và cấu hình biên dịch: `record` đã chính thức, **không cần `--enable-preview`**. Trong các bản Java được hỗ trợ về sau, cú pháp cơ bản này vẫn áp dụng.
4. Mỗi bản preview thuộc về chính bản JDK tương ứng và có thể có điều chỉnh. Khi hiện đại hóa mã nguồn thử nghiệm cũ, hãy **biên dịch lại và kiểm thử với JDK đích**; không coi tệp `.class` từ preview là một định dạng nhị phân ổn định để tái sử dụng trên JDK mới.

Lịch sử của preview giúp hiểu nguồn gốc thiết kế, còn **quy tắc triển khai trong các phần tiếp theo đều là quy tắc records chính thức của Java 16+**.

## 3. Record chính thức là gì và trình biên dịch tạo ra gì?

Với khai báo:

```java
public record Product(String code, long price) {}
```

trình biên dịch cung cấp những thành phần mà người viết lớp dữ liệu thông thường thường phải tự viết:

- **Hai trường thành viên:** `private final String code` và `private final long price`. Trường không thể được gán lại sau khi constructor hoàn tất.
- **Canonical constructor** có chữ ký tương ứng với danh sách component: `new Product(String code, long price)`.
- **Accessor**: `code()` và `price()`, **không tự sinh** các getter theo mẫu JavaBeans như `getCode()` hay `getPrice()`.
- **`equals(Object)` và `hashCode()`** dựa trên các component, cho phép so sánh dữ liệu của hai đối tượng cùng loại record; với component kiểu đối tượng, ngữ nghĩa so sánh tuân theo kiểu dữ liệu của component.
- **`toString()`** biểu diễn tên record và các component để thuận tiện theo dõi/log. Không nên viết kiểm thử nghiệp vụ dựa vào dấu câu hoặc định dạng chính xác của chuỗi trả về.

Ví dụ đơn giản (đoạn mã đặt trong thân phương thức):

```java
Product a = new Product("B001", 120_000);
Product b = new Product("B001", 120_000);

System.out.println(a.code());       // B001
System.out.println(a.price());      // 120000
System.out.println(a.equals(b));    // true
```

**Record vẫn là class**: nó có thể khai báo phương thức, thực thi giao diện (`implements`), dùng generic, khai báo thành viên `static` và chứa các kiểu lồng nhau. Mỗi record kế thừa trực tiếp `java.lang.Record` theo quy tắc của ngôn ngữ và mặc định là `final`, nên **không thể kế thừa từ record đó hoặc dùng `extends SomeClass` để chọn lớp cha khác**.

Một record phù hợp nhất khi **trạng thái được xác định hoàn toàn bởi các component**: tọa độ, khoảng giá trị, kết quả tính toán, cấu hình bất biến, đối tượng kết quả API hoặc dữ liệu truyền giữa các tầng. Nếu đối tượng cần thay đổi trường theo vòng đời, thêm các trường instance ẩn ngoài phần đầu hoặc dựa vào setter, class thông thường có thể phù hợp hơn.

### So với một lớp Java tự viết

Nếu dùng class cho `Product`, ta thường tự khai báo trường `final`, constructor, getter/accessor, `equals`, `hashCode`, `toString`. Record loại bỏ phần mã lặp nhưng **không thay thế** việc thiết kế bất biến nghiệp vụ, chọn kiểu dữ liệu đúng và đánh giá các ràng buộc API.

**Không hiểu nhầm:** record **không phải primitive hay value type**. Nó là kiểu tham chiếu và đối tượng vẫn có danh tính ở mức Java object; việc `equals` so sánh các component không biến record thành kiểu dữ liệu nguyên thủy.

## 4. Ví dụ Java 16+ hoàn chỉnh: dữ liệu ổn định, chuẩn hóa và local record

Ví dụ sau có thể **biên dịch và chạy nguyên vẹn** bằng JDK 16 trở lên. Các API `List.copyOf` và `String.strip` cũng đã có sẵn trước Java 16.

Tạo tệp **`RecordEvolutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RecordEvolutionDemo {
    // Record lồng trong class: mặc định là static.
    public record Member(String id, List<String> roles) {
        // Compact canonical constructor: kiểm tra và chuẩn hóa input.
        public Member {
            id = Objects.requireNonNull(id, "id").strip();
            if (id.isEmpty()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            roles = List.copyOf(Objects.requireNonNull(roles, "roles"));
        }

        // Record vẫn có thể khai báo instance method.
        public String displayLabel() {
            return "Member:" + id;
        }
    }

    static String summarize(int count) {
        // Local record: cú pháp đã được bổ sung ở Java 15.
        record Summary(int count, boolean active) { }
        Summary result = new Summary(count, count > 0);
        return result.count() + ":" + result.active();
    }

    public static void main(String[] args) {
        ArrayList<String> original = new ArrayList<>(List.of("reader", "editor"));
        Member first = new Member("  A42  ", original);
        Member second = new Member("A42", List.of("reader", "editor"));
        original.add("admin");

        System.out.println(first.id());
        System.out.println(first.roles());
        System.out.println(first.roles().contains("admin"));
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first.displayLabel());
        System.out.println(summarize(3));
    }
}
```

**Biên dịch và chạy** (JDK 16+):

```bash
javac --release 16 -encoding UTF-8 RecordEvolutionDemo.java
java RecordEvolutionDemo
```

`--release 16` yêu cầu `javac` của JDK 16 hoặc mới hơn và dùng tính năng ngôn ngữ/API tương thích với Java 16. Có thể bỏ `--release 16` nếu dự án chủ ý dùng phiên bản đích là JDK hiện tại, nhưng với ví dụ đối chiếu lịch sử thì tùy chọn này làm mốc phiên bản rõ ràng. **Không cần bật preview**.

**Đầu ra chính xác:**

```text
A42
[reader, editor]
false
true
true
Member:A42
3:true
```

**Giải thích từng cơ chế:**

1. `Member` là một record lồng trong `RecordEvolutionDemo`. Record lồng mặc định `static`, nên không cần đối tượng bao ngoài để tạo `Member`.
2. Hai component là `id` và `roles`. Accessor tự sinh lần lượt là `id()` và `roles()`.
3. **Compact constructor** `public Member { ... }` nhận các tham số ngầm định từ header record. `id = ...strip()` chuẩn hóa tham số; `roles = List.copyOf(...)` tạo danh sách không thể thêm/bớt phần tử sau khi lưu. Cuối thân compact constructor, compiler tự gán các tham số đã chuẩn hóa vào trường tương ứng.
4. `original.add("admin")` thay đổi danh sách đầu vào **sau** khi tạo `first`. Do `roles` đã được chụp bằng `List.copyOf`, component của `first` vẫn là `[reader, editor]`, nên phép `contains("admin")` trả `false`.
5. `first.equals(second)` là `true` vì `id` chuẩn hóa giống nhau và `List.equals` so sánh phần tử theo thứ tự. Khi hai đối tượng bằng nhau theo `equals`, `hashCode` phải bằng nhau, nên dòng tiếp theo cũng là `true`.
6. `displayLabel()` là phương thức do ta tự viết thêm vào record, trả chuỗi `Member:A42`.
7. `Summary` là **local record** được khai báo ngay trong phương thức `summarize`. Trường hợp này minh họa phần mở rộng từ Java 15 vẫn có giá trị trong Java 16+; `result.count()` trả `3`, `result.active()` trả `true`.

### Compact canonical constructor có tác dụng gì?

Khi chỉ cần kiểm tra hoặc chuẩn hóa dữ liệu trước khi lưu, compact constructor giúp tránh viết lại toàn bộ tham số và phép gán. Trong ví dụ:

```java
public Member {
    id = Objects.requireNonNull(id, "id").strip();
    if (id.isEmpty()) {
        throw new IllegalArgumentException("id must not be blank");
    }
    roles = List.copyOf(Objects.requireNonNull(roles, "roles"));
}
```

Ở cuối block, các trường `this.id` và `this.roles` được compiler tự khởi tạo từ tham số `id` và `roles`. **Không tự viết `this.id = id;` trong compact constructor**: việc gán trực tiếp vào component field tại đây là lỗi biên dịch của record chính thức. Nếu muốn tự gán tất cả component fields, dùng **canonical constructor dạng đầy đủ** với danh sách tham số và quy tắc definite assignment.

## 5. Các đặc điểm chính thức cần nắm để dùng record đúng

### 5.1. Bất biến của record là *shallow immutability*

Các trường của record là `final`, nhưng **đối tượng mà một trường tham chiếu tới có thể vẫn thay đổi**:

```java
// Ví dụ minh họa rủi ro; không phải cách thiết kế nên dùng.
record UnsafeMember(List<String> roles) {}

List<String> source = new ArrayList<>();
source.add("reader");
UnsafeMember member = new UnsafeMember(source);
source.add("admin");

// member.roles() vẫn trỏ tới danh sách source đã thay đổi.
System.out.println(member.roles()); // [reader, admin]
```

`final` chỉ ngăn **gán lại tham chiếu `roles`**, không khiến `ArrayList` trở thành bất biến. Đó là lý do ví dụ đầy đủ chủ động gọi `List.copyOf`.

Ngay cả với `List.copyOf`, nếu **phần tử trong danh sách là đối tượng mutable**, các phần tử vẫn có thể bị sửa từ nơi khác. Muốn bất biến sâu, cần thiết kế kiểu phần tử bất biến hoặc tạo bản sao phù hợp của chúng. Tương tự, component là **mảng** có thể bị sửa qua tham chiếu; `equals` tự sinh cho mảng không tự thực hiện so sánh nội dung sâu. Không chọn mảng mutable trong record chỉ vì cú pháp ngắn gọn.

### 5.2. Constructor: canonical, compact và constructor bổ sung

Record có **canonical constructor** tương ứng với các component. Có hai cách định nghĩa tường minh:

**Dạng đầy đủ:** tự liệt kê tham số và tự gán mọi trường thành phần.

```java
public record Range(int min, int max) {
    public Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must be <= max");
        }
        this.min = min;
        this.max = max;
    }
}
```

**Dạng compact:** khai báo tên record, bỏ danh sách tham số và để compiler tự gán:

```java
public record Range(int min, int max) {
    public Range {
        if (min > max) {
            throw new IllegalArgumentException("min must be <= max");
        }
    }
}
```

Hai ví dụ là **hai cách thay thế để định nghĩa cùng một record**, không đặt chung trong một tệp với cùng tên record. Khi viết `public record`, canonical constructor công khai cũng phải có mức truy cập phù hợp.

Record còn có thể có **constructor bổ sung**, nhưng constructor này phải ủy quyền đến constructor khác của chính record bằng `this(...)`, để quá trình khởi tạo luôn đi qua canonical constructor:

```java
public record Size(int width, int height) {
    public Size(int edge) {
        this(edge, edge);
    }
}
```

Nếu muốn kiểm tra giá trị, hãy kiểm tra ở canonical/compact constructor để cả `new Size(3)` và `new Size(3, 3)` đều được kiểm soát nhất quán.

### 5.3. Giới hạn cấu trúc record

Các quy tắc sau **vẫn có hiệu lực trên Java hiện đại**:

- Record **ngầm định `final`**; không thể kế thừa record hoặc cho record `extends` một class khác.
- Record **không cho khai báo trường instance bổ sung** ngoài các trường sinh từ component và **không cho instance initializer**. Thành viên `static` và instance method thông thường được phép.
- Record có thể **`implements` interface**, dùng generic và khai báo phương thức bổ sung.
- Không có setter tự sinh. Setter hay trường instance mutable phụ thường đi ngược mục đích mô hình dữ liệu của record.
- Record **không tự động triển khai `java.io.Serializable`**. Nếu chủ động `implements Serializable`, cơ chế serialization của record dựa trên các component và khi deserialize sẽ gọi canonical constructor; không áp dụng hoàn toàn cách tùy biến serialization của class thường.
- `record` là **lớp dữ liệu**, không phải một “data class” tự động bảo đảm mọi điều kiện bảo mật, tính hợp lệ hay khả năng bất biến sâu. Trách nhiệm xác thực dữ liệu vẫn thuộc về thiết kế ứng dụng.

### 5.4. Local record và record lồng nhau

Tính năng **local record** được bổ sung trong preview Java 15 và tiếp tục được hỗ trợ ổn định:

```java
// Đoạn minh họa trong một phương thức.
record ItemTotal(String sku, long amount) {}

ItemTotal total = new ItemTotal("SKU-1", 150_000);
System.out.println(total.amount()); // 150000
```

Local record **ngầm định `static`**, nên nó không tự “bắt” (capture) các biến cục bộ hay `this` của ngữ cảnh bao quanh như local class thông thường. Hãy truyền dữ liệu vào qua record component. Điều này phù hợp khi tạo một kiểu trung gian nhỏ cho phép tính, gom nhóm, sắp xếp hoặc kết quả của stream.

**Record là thành viên trong một inner class** cũng được phép từ Java 16 nhờ thay đổi quy tắc thành viên `static` trong inner class. Đây là một điểm hoàn thiện của JEP 395: cách tổ chức kiểu lồng nhau nhất quán hơn với các class Java hiện đại.

## 6. Chuyển mã sử dụng preview Java 14/15 sang Java 16+ cần chú ý gì?

Nếu đang đọc repository cũ có khai báo `record` từ giai đoạn preview, hướng xử lý thực tế là **giữ mô hình dữ liệu hợp lý, kiểm chứng lại mã nguồn theo ngữ nghĩa chính thức, biên dịch và kiểm thử trên JDK hỗ trợ**, thay vì tiếp tục dựa vào cấu hình preview cũ.

| Hạng mục | Điều cần xác nhận khi nâng cấp |
| --- | --- |
| **JDK biên dịch và chạy** | Dự án sử dụng Java 16+ (thực tế nên dùng JDK có chính sách hỗ trợ phù hợp, chẳng hạn Java 17/21/25 tùy dự án); record cơ bản không còn yêu cầu `--enable-preview` |
| **Mã record cũ** | Kiểm tra các constructor, mức truy cập, lệnh gán component field, record lồng nhau và local record theo quy tắc chính thức; biên dịch lại thay vì giả định mọi source preview sẽ tương thích 100% |
| **Cấu hình build** | Đặt source/target hoặc `--release` phù hợp với JDK tối thiểu cần hỗ trợ; không lấy cờ preview của Java 14/15 làm yêu cầu biên dịch hiện tại |
| **Public API** | Accessor của record là `componentName()`, không tự động là `getComponentName()`; kiểm tra mọi caller, serializer, mapper hoặc framework dùng reflection |
| **Tương thích mô hình** | Đổi class sang record có thể thay đổi cơ chế equals/hashCode, constructor, subclassing, cách khởi tạo, khả năng gán lại trạng thái và tương thích nhị phân |
| **Component thay đổi** | Thêm, xóa, đổi tên, đổi kiểu hoặc đổi thứ tự component có thể ảnh hưởng constructor, accessor, cách so sánh, serialization và các caller; xem là thay đổi API cần đánh giá |
| **Bất biến thật sự** | Với `List`, `Map`, mảng hoặc đối tượng mutable, phải xem xét defensive copy/validation thay vì nghĩ `final` là đủ |
| **Kiểm thử** | Kiểm tra cả trường hợp hợp lệ, giá trị thiếu, dữ liệu mutable, equality/hashCode và hợp đồng của các API gọi record |

**Ví dụ cấu hình biên dịch theo Java 16** từ một JDK mới:

```bash
javac --release 16 -encoding UTF-8 RecordEvolutionDemo.java
java RecordEvolutionDemo
```

Lệnh trên trình bày **ngữ nghĩa record chính thức**. Nếu dự án chạy Java 17 hoặc 21, có thể đặt `--release 17`/`--release 21` tương ứng và dùng những API/tính năng mà phiên bản đó hỗ trợ. Đừng nhầm **phiên bản đầu tiên có tính năng** với **phiên bản dự án bắt buộc phải sử dụng**.

### Vì sao chuyển class thành record không chỉ là đổi cú pháp?

Hãy tưởng tượng một class `User` trước đây có constructor rỗng, setter, trường `id` thay đổi sau khi tạo và `equals` chỉ xét `id`. Nếu đổi thành `record User(String id, String name)`:

- Cách xây dựng đối tượng thay đổi thành canonical constructor nhận đủ component, trừ khi chủ động viết constructor bổ sung.
- `id()` và `name()` là accessor tự sinh; những caller dùng `getId()` không tự nhiên hoạt động nếu không bổ sung adapter thích hợp.
- `equals` tự sinh xét **cả `id` và `name`**, không còn chỉ xét `id` như class cũ.
- Các component không có setter và record không hỗ trợ trường instance mở rộng ngoài header.

Vì thế chỉ nên chuyển khi **hợp đồng dữ liệu** mới tương thích với những nơi sử dụng. Đặc biệt, đừng tự động thay mọi entity ORM có vòng đời mutable hoặc mọi JavaBean đòi setter/constructor rỗng bằng record mà chưa kiểm tra yêu cầu của thư viện.

## 7. Những hiểu nhầm dễ gặp

| Nhận định dễ nhầm | Điều đúng và vẫn áp dụng |
| --- | --- |
| “Records là tính năng chính thức từ Java 14” | **Java 14 preview; Java 15 second preview; Java 16 chính thức** |
| “Java 16 vẫn phải bật preview để dùng record” | **Không**. Record cơ bản là tính năng chuẩn từ Java 16 |
| “Record bất biến tuyệt đối” | Trường component là `final`; đối tượng mutable mà trường trỏ tới vẫn có thể biến đổi nếu không phòng vệ |
| “Record giống `struct` hoặc primitive” | Record là một class tham chiếu đặc biệt, ngầm định `final` và kế thừa `java.lang.Record` |
| “Record tự có `getId()`/`setId()`” | Accessor tự sinh là `id()`, không có setter tự sinh |
| “Compact constructor phải viết `this.id = id;`” | Compiler tự gán component fields ở cuối compact constructor; gán trực tiếp vào chúng ở đây là không hợp lệ |
| “Local record chỉ dùng được trong các bản preview cũ” | Tính năng local record tiếp tục có mặt trong Java 16+ |
| “Đổi tên hay thứ tự component chắc chắn không ảnh hưởng API” | Component định hình constructor, accessor, equality và hợp đồng dữ liệu; thay đổi cần đánh giá tương thích |
| “Record phù hợp với mọi entity trong hệ thống” | Record phù hợp nhất cho dữ liệu ổn định, mô hình dựa trên component; entity có vòng đời mutable cần thiết kế riêng |
| “Record tự động có thể serialize qua Java Serialization” | Phải triển khai `Serializable` nếu muốn dùng cơ chế đó; record có quy tắc serialization riêng |

## 8. Khi nào nên dùng record trong Java hiện đại?

**Nên cân nhắc record** khi đối tượng đại diện cho một bộ giá trị rõ ràng, chẳng hạn `Coordinate`, `Money`, `PageResult`, `SearchCriteria` hoặc kết quả tạm giữa các bước tính toán; các thành phần đủ mô tả danh tính dữ liệu, và không cần trạng thái instance ẩn hoặc setter.

**Cân nhắc class thường** khi đối tượng bắt buộc thay đổi trạng thái liên tục, có quan hệ kế thừa class, cần khởi tạo theo vòng đời phức tạp hoặc khi framework hiện có yêu cầu cơ chế mà record không cung cấp mặc định.

**Ba câu tự kiểm tra:**

1. **`record` ở Java 14 và Java 16 có cùng trạng thái ổn định không?** Không. Java 14 là preview lần một, Java 16 là chính thức; cú pháp record cơ bản có thể sử dụng không cần preview từ Java 16.
2. **`List.copyOf` trong compact constructor nhằm giải quyết gì?** Tạo danh sách không cho sửa tập phần tử qua record và ngăn danh sách nguồn mutable bị sửa sau đó làm thay đổi nội dung component; nó chưa tạo bất biến sâu cho phần tử mutable.
3. **Vì sao `record Member(String id, List<String> roles)` tự có `id()`, nhưng chưa chắc thay thế an toàn class `Member` cũ?** Vì caller, constructor, setter, equality, kế thừa và framework có thể trông đợi hợp đồng khác. Cần kiểm tra toàn bộ nơi sử dụng.

## 9. Tài liệu chính thức

- [JEP 359 — Records (Preview)](https://openjdk.org/jeps/359): mốc giới thiệu tại Java 14 (bối cảnh lịch sử).
- [JEP 384 — Records (Second Preview)](https://openjdk.org/jeps/384): mốc Java 15, bao gồm local records (bối cảnh lịch sử).
- [JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế records được chuẩn hóa tại Java 16.
- [Oracle — Java 16 Language Changes](https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html): xác nhận record được chuẩn hóa và không còn cần preview từ Java 16.
- [Oracle — Record Classes (Java 25)](https://docs.oracle.com/en/java/javase/25/language/records.html): constructor, component, biến bất biến ở mức shallow, local record, kiểu lồng và quy tắc hiện hành.
