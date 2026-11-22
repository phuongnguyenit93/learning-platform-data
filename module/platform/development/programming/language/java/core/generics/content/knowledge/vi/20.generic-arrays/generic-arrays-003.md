# Vì sao không thể trực tiếp tạo `new List<String>[]` trong Java Generics?

## 1. Vấn đề cụ thể

Ta có thể tạo mảng chứa `String`:

```java
String[] words = new String[3];
```

Ta cũng có thể tạo một danh sách chứa `String`:

```java
java.util.List<String> words = new java.util.ArrayList<>();
```

Nhưng ghép hai ý tưởng lại thành:

```java
// CỐ Ý KHÔNG HỢP LỆ: đây là ví dụ lỗi biên dịch.
java.util.List<String>[] groups = new java.util.List<String>[3];
```

thì `javac` báo **generic array creation**. `List<String>[]` là kiểu có thể xuất hiện trong khai báo biến, tham số hay kết quả phương thức ở những ngữ cảnh phù hợp, nhưng **không được trực tiếp tạo mảng có kiểu phần tử là `List<String>`** bằng biểu thức `new List<String>[3]`.

Vì sao? Hai cơ chế được thiết kế theo hai thời điểm khác nhau:

- **Mảng Java có kiểu phần tử được kiểm tra lúc chạy.** Một mảng thực sự biết component type runtime của nó; JVM dùng thông tin đó để kiểm tra khi gán vào một phần tử.
- **Generics thông thường được kiểm tra chủ yếu khi biên dịch.** Thông tin đối số `<String>` trên một `List<String>` bị xóa khỏi kiểu đại diện dùng cho kiểm tra runtime thông thường.

Nếu Java cho phép tạo mảng trực tiếp với component type `List<String>`, JVM sẽ không có đủ thông tin để bảo vệ lời hứa “mọi phần tử là danh sách chuỗi” khi mảng được truy cập thông qua các tham chiếu kiểu rộng hơn. Cấm trực tiếp tạo loại mảng đó là một phần của thiết kế giữ an toàn kiểu giữa **array covariance**, **runtime store checks** và **generic erasure**.

**Phân biệt quan trọng:** Việc *khai báo* `List<String>[] groups;` hợp lệ không đồng nghĩa với việc biểu thức `new List<String>[3]` hợp lệ.

## 2. Hai quy tắc nền tảng: mảng biết component type, generic không reify đối số kiểu

Một mảng được tạo như sau:

```java
String[] a = new String[2];
Number[] b = new Integer[2];
```

Object mảng thực sự mang runtime array class như `[Ljava.lang.String;` hoặc `[Ljava.lang.Integer;`. Khi JVM nhận một thao tác gán phần tử, nó có thể kiểm tra object được đưa vào có phù hợp runtime component type hay không.

Ngược lại:

```java
java.util.List<String> text = new java.util.ArrayList<>();
java.util.List<Integer> nums = new java.util.ArrayList<>();
```

Hai biến có kiểu generic khác nhau tại thời điểm biên dịch, nhưng khi thực thi, cả hai object đều có runtime class `java.util.ArrayList`. `getClass()` trên từng object không trả về `ArrayList<String>` hoặc `ArrayList<Integer>` như hai class tách biệt.

Từ Java Language Specification:

- `List<String>` là **non-reifiable type**: không thể biểu diễn đầy đủ đối số generic `String` để runtime kiểm tra như component type của mảng.
- `List<?>` với **wildcard không giới hạn** là một ví dụ kiểu **reifiable**; kiểm tra runtime chỉ cần biết raw `List`, không cần xác nhận một đối số kiểu cụ thể.
- Một biểu thức tạo mảng với `new` phải có component type **reifiable**.

Từ các quy tắc này, `new List<String>[3]` bị cấm, còn `new List<?>[3]` được phép. Điều này không phải một giới hạn tùy ý của IDE; đó là ràng buộc ngôn ngữ Java.

## 3. Đối chiếu mảng hiệp biến với generics bất biến

### 3.1. Arrays là covariant

Trong Java, nếu `String` là subtype của `Object`, thì `String[]` là subtype của `Object[]`:

```java
String[] names = new String[1];
Object[] objects = names; // Hợp lệ.
```

**Array covariance** cho phép phép gán đó ở compile time. Nhưng JVM vẫn giữ component type thực tế của mảng là `String` để kiểm tra thao tác lưu phần tử.

Nếu code sau thực hiện:

```java
objects[0] = Integer.valueOf(42);
```

thì JVM thấy một `Integer` không thể được lưu vào mảng `String[]` và ném `ArrayStoreException`.

Điều kiện runtime này ngăn mảng `String[]` bị chứa một phần tử không phải `String`, dù tham chiếu `Object[]` rộng hơn được dùng.

### 3.2. Generics thường invariant

Ngược lại:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
// java.util.List<Object> objects = strings; // KHÔNG hợp lệ.
```

`List<String>` **không** phải subtype của `List<Object>`: Java Generics mặc định **invariant**. Nếu phép gán bị cấm này được cho phép, có thể gọi `objects.add(42)` rồi làm hỏng hợp đồng chuỗi của `strings`.

Để đọc những danh sách chưa biết kiểu phần tử, Java cung cấp wildcard:

```java
java.util.List<?> unknown = strings;
Object first = unknown.isEmpty() ? null : unknown.get(0);
```

`List<?>` chấp nhận danh sách với đối số kiểu chưa xác định, nhưng không cho thêm tùy tiện `Integer` hay `String` vào đó.

### 3.3. Vì sao kết hợp hai mô hình gây nguy hiểm?

Mảng có cơ chế kiểm tra **runtime component type**; danh sách generic có **compile-time type argument** bị erasure. Một mảng có component type là `List<String>` muốn bảo vệ hoàn toàn an toàn kiểu thì sẽ cần phân biệt `List<String>` với `List<Integer>` trong runtime array store check. Nhưng cơ chế type erasure không cung cấp sự phân biệt ấy.

Không được suy ra rằng “mảng không bao giờ an toàn” hoặc “generics không bao giờ an toàn”. Hai cơ chế đều an toàn trong phạm vi các quy tắc của mình; vấn đề là một biểu thức tạo mảng mới **không thể cam kết kiểm tra runtime** cho đối số generic non-reifiable.

## 4. Chương trình chạy được: `ArrayStoreException` trên mảng reifiable

Tạo tệp **`ArrayStoreCheckDemo.java`**:

```java
public class ArrayStoreCheckDemo {
    public static void main(String[] args) {
        String[] words = new String[2];
        words[0] = "Java";

        Object[] alias = words;

        try {
            alias[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }

        System.out.println(words[0]);
        System.out.println(words[1] == null);
        System.out.println(words.getClass().getComponentType().getName());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ArrayStoreCheckDemo.java
java ArrayStoreCheckDemo
```

Stdout chính xác:

```text
ArrayStoreException
Java
true
java.lang.String
```

Giải thích theo thứ tự:

1. `words` được tạo bằng `new String[2]`, nên **component type runtime** là `String`.
2. `Object[] alias = words` hợp lệ do array covariance. Cả hai biến trỏ tới **cùng mảng**.
3. `alias[1] = Integer.valueOf(42)` biên dịch được do kiểu tĩnh `Object[]`, nhưng lúc chạy JVM kiểm tra thực tế là `String[]`.
4. JVM ném `ArrayStoreException`; phần tử vị trí 1 vẫn là `null`.
5. Reflection trên object mảng trả component type là `String`.

Runtime biết đủ thông tin để ngăn thao tác sai. Đây là điểm khác cơ bản với một object `ArrayList<String>` thông thường.

## 5. Thử tạo `new List<String>[3]`: lỗi xảy ra trước khi chạy

Ví dụ **cố ý không biên dịch** trong tệp `InvalidGenericArray.java`:

```java
import java.util.List;

public class InvalidGenericArray {
    public static void main(String[] args) {
        List<String>[] groups = new List<String>[3];
    }
}
```

Nếu chạy:

```bash
javac InvalidGenericArray.java
```

Trình biên dịch từ chối biểu thức tạo mảng và thường báo:

```text
generic array creation
```

Đây là **mẩu thông điệp lỗi minh họa**, không cam kết nguyên văn toàn bộ output `javac`: vị trí mũi tên, số dòng và cách trình bày tùy compiler/version.

Đặc biệt, việc biểu thức vế trái là `List<String>[]` **không phải lỗi chính**. Phần không hợp lệ là **`new List<String>[3]`**, bởi `List<String>` là component type non-reifiable.

Các dạng tạo mảng khác cũng không hợp lệ vì component type mang thông tin generic không reifiable:

```java
// CỐ Ý KHÔNG HỢP LỆ — chỉ để phân tích.
new java.util.List<Integer>[2];
new java.util.List<? extends Number>[2];
new java.util.Map<String, Integer>[4];
```

Ngược lại, các khai báo sau **có thể hợp lệ** nếu được đặt trong ngữ cảnh Java phù hợp:

```java
java.util.List<String>[] declared;
java.util.List<String>[] parameter = null;
```

Một khai báo biến kiểu mảng generic không tự tạo đối tượng mảng runtime. Những phép gán về sau vẫn phải thỏa các quy tắc kiểu của Java, và có thể dẫn tới cảnh báo unchecked nếu dùng một đường vòng.

## 6. Kiểu reifiable: tại sao `List<?>[]` được phép?

Java định nghĩa **reifiable types** là các kiểu được biểu diễn đủ ở runtime theo quy tắc ngôn ngữ. Những ví dụ thích hợp trong bối cảnh này:

| Component type | `new ComponentType[n]` | Giải thích |
|---|---|---|
| `String` | Hợp lệ | Runtime biết `String` |
| `Integer` | Hợp lệ | Runtime biết `Integer` |
| Raw `List` | Hợp lệ, có thể có cảnh báo rawtypes | Runtime biết raw `List` |
| `List<?>` | Hợp lệ | Parameterization chỉ dùng wildcard không giới hạn |
| `List<String>` | Không hợp lệ | Không reifiable |
| `List<Integer>` | Không hợp lệ | Không reifiable |
| `List<? extends Number>` | Không hợp lệ | Wildcard có upper bound cụ thể, không thuộc dạng reifiable này |
| Type variable `T` | Không hợp lệ khi viết `new T[n]` | Không có class runtime cụ thể của `T` để tạo array component |

Vì vậy, dòng sau hợp lệ:

```java
java.util.List<?>[] groups = new java.util.List<?>[3];
```

Điều này **không** có nghĩa mảng runtime nhớ từng danh sách bên trong có phần tử kiểu gì. Thành phần của mảng là một `List<?>` — một danh sách với đối số kiểu không xác định, chỉ cần runtime kiểm tra object được lưu là một `List` hợp lệ.

Nên đọc dấu `<?>` chính xác: “một kiểu phần tử chưa biết” khác với “một kiểu phần tử là `Object`”. `List<?>` vẫn giữ các hạn chế generic có ích khi thao tác thêm phần tử.

## 7. Chương trình chạy được: mảng `List<?>[]` hợp lệ

Tạo tệp **`WildcardListArrayDemo.java`**:

```java
import java.util.List;

public class WildcardListArrayDemo {
    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];

        groups[0] = List.of("A", "B");
        groups[1] = List.of(10, 20);

        System.out.println(groups[0].size());
        System.out.println(groups[1].get(0));
        System.out.println(groups.getClass().getComponentType().getName());

        Object[] alias = groups;

        try {
            alias[0] = "not a list";
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }

        System.out.println(groups[0]);
    }
}
```

Lệnh:

```bash
javac WildcardListArrayDemo.java
java WildcardListArrayDemo
```

Stdout:

```text
2
10
java.util.List
ArrayStoreException
[A, B]
```

Giải thích:

- Hai danh sách có kiểu phần tử khác nhau đều phù hợp với `List<?>`.
- Lời gọi `groups[1].get(0)` có kiểu tĩnh an toàn là `Object`, nhưng `println(Object)` vẫn in được giá trị `10`.
- `groups.getClass().getComponentType()` trả `java.util.List`: mảng runtime biết lớp/interface `List`, **không có `String` hoặc `Integer` trong component type**.
- Truy cập qua `Object[]` vẫn phải tuân thủ runtime array store check. String `"not a list"` không phải một `List`, nên bị từ chối.
- `List.of("A","B")` là danh sách không thể sửa qua thao tác cấu trúc thông thường. Ví dụ chỉ đọc, không sửa nội dung danh sách.

### Điều mảng wildcard này không bảo đảm

`List<?>[]` không có nghĩa “mọi slot chứa `List<String>`”. Trên thực tế, ví dụ chủ động đặt một `List<String>` vào slot 0 và một `List<Integer>` vào slot 1.

Nếu nhu cầu là các danh sách **đồng nhất có phần tử `String`**, `List<?>[]` không giải quyết đầy đủ hợp đồng kiểu. Hãy dùng cấu trúc generic phù hợp hơn, ví dụ `List<List<String>>`.

## 8. Vì sao cho phép `new List<String>[]` sẽ gây heap pollution?

Hãy mô phỏng tình huống mà Java đang ngăn chặn. Giả sử tồn tại một mảng `List<String>[]`, rồi tham chiếu rộng hơn `Object[]` lưu vào đó một `List<Integer>`.

Mảng runtime sẽ biết component type đã bị xóa là **raw `List`**. `List<Integer>` vẫn là một đối tượng `List`, nên **array store check không có lý do để bác bỏ**. Nhưng mã đọc qua kiểu `List<String>[]` sẽ mong `String`, tạo nguy cơ `ClassCastException` muộn hơn.

Ta có thể minh họa cơ chế bằng một **unchecked cast được khoanh vùng**; đây không phải cách khuyến nghị tạo mảng generic.

Tạo tệp **`GenericArrayPollutionDemo.java`**:

```java
import java.util.List;

public class GenericArrayPollutionDemo {

    @SuppressWarnings("unchecked")
    static List<String>[] unsafeArray() {
        return (List<String>[]) new List<?>[1];
    }

    public static void main(String[] args) {
        List<String>[] stringLists = unsafeArray();
        stringLists[0] = List.of("safe");

        Object[] arrayAlias = stringLists;

        arrayAlias[0] = List.of(123);

        System.out.println(stringLists.getClass()
                .getComponentType().getName());
        System.out.println(stringLists[0].size());

        try {
            String text = stringLists[0].get(0);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac GenericArrayPollutionDemo.java
java GenericArrayPollutionDemo
```

Stdout:

```text
java.util.List
1
ClassCastException
```

Phân tích chính xác:

1. `new List<?>[1]` hợp lệ vì component type `List<?>` là reifiable.
2. Ép sang `List<String>[]` là **unchecked cast**: runtime không thể xác minh `<String>` cho các phần tử.
3. `stringLists[0] = List.of("safe")` hợp lệ với kiểu tĩnh của biến.
4. `Object[] arrayAlias = stringLists` hợp lệ do array covariance.
5. `arrayAlias[0] = List.of(123)` không gây `ArrayStoreException`: object là một `List`, phù hợp với raw component runtime của mảng.
6. Truy cập `stringLists[0].get(0)` ở mã nguồn được kiểm tra theo `List<String>`, và phép cast cần thiết sang `String` thất bại khi giá trị thực là `Integer`.

Trạng thái nơi tham chiếu có kiểu `List<String>[]` nhưng phần tử trong mảng không thỏa hợp đồng generic là một dạng **heap pollution**.

`@SuppressWarnings("unchecked")` chỉ giấu cảnh báo ở đoạn chuyển kiểu đã biết nguy hiểm. Annotation này không biến phép cast thành an toàn và không bổ sung kiểm tra runtime nào. Trong ứng dụng thực, tránh mẫu `unsafeArray()` nếu có lựa chọn thiết kế khác.

### Tại sao lỗi không xuất hiện tại lúc lưu `List<Integer>`?

Runtime biết component là `List`, chứ không biết `List<String>` khác `List<Integer>`. Bởi vậy JVM có thể nhận object thuộc `List`. Lỗi phát sinh khi mã nguồn dùng hợp đồng `String` trong quá trình đọc.

Đây là lý do mấu chốt của quy tắc cấm trực tiếp `new List<String>[n]`: ngôn ngữ không muốn cấp phát hợp pháp một mảng có vẻ mang cam kết type argument mà runtime array store check không thể bảo đảm.

## 9. Khai báo `List<String>[]` hợp lệ nhưng việc khởi tạo có giới hạn

Nhiều người học Java gặp một nghịch lý:

```java
List<String>[] groups; // Hợp lệ.
```

nhưng:

```java
// Cố ý không hợp lệ:
groups = new List<String>[10];
```

Điều này hoàn toàn nhất quán: type checker cho phép **kiểu biến** là một array of parameterized type trong nhiều ngữ cảnh, nhưng biểu thức tạo mảng mới đòi **component type reifiable**.

Một biến `List<String>[]` có thể xuất hiện khi:

- Được truyền vào phương thức từ một API cũ.
- Được hình thành từ một thao tác cast không được kiểm tra đầy đủ.
- Đi qua một API generic varargs, nơi compiler xử lý bằng quy tắc riêng.
- Là phần của dữ liệu nội bộ của một thư viện phải tương thích với mảng.

Không nên suy luận rằng mọi đối tượng được gán cho biến ấy đều an toàn. Sự tồn tại của type annotation ở biến không khôi phục `<String>` trong runtime component type.

### Dùng raw array có được không?

Ví dụ:

```java
java.util.List[] raw = new java.util.List[2];
```

Là cú pháp cho phép tạo mảng có component type raw `List`, nhưng **raw type bỏ kiểm tra generic** ở các thao tác. Nếu cố gán raw array vào `List<String>[]`, compiler có thể cảnh báo unchecked conversion, và rủi ro của ví dụ heap pollution vẫn còn.

Tránh coi `new List[n]` hoặc ép `(List<String>[]) new List[n]` là “mẹo sửa triệt để”. Nó chỉ đưa trách nhiệm an toàn kiểu ra khỏi sự chứng minh của compiler.

## 10. Giải pháp thông thường: `List<List<String>>`

Đối với ứng dụng thực tế cần “một tập các danh sách chuỗi”, ta thường **không cần array**. Dùng collection lồng nhau:

```java
List<List<String>> groups = new ArrayList<>();
```

Compiler giữ được quan hệ kiểu ở cả hai cấp:

- Outer list nhận các phần tử thuộc `List<String>`.
- Inner list nhận các phần tử `String`.
- Không cần tạo array component type non-reifiable.

Tạo tệp **`ListOfListsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListOfListsDemo {
    public static void main(String[] args) {
        List<List<String>> groups = new ArrayList<>();

        groups.add(new ArrayList<>(List.of("Java", "Kotlin")));
        groups.add(new ArrayList<>(List.of("Spring")));

        groups.get(1).add("Micronaut");

        for (List<String> group : groups) {
            System.out.println(String.join(", ", group));
        }

        System.out.println(groups.size());
        System.out.println(groups.get(0).get(1));
    }
}
```

Biên dịch/chạy:

```bash
javac ListOfListsDemo.java
java ListOfListsDemo
```

Stdout:

```text
Java, Kotlin
Spring, Micronaut
2
Kotlin
```

Nếu thử thêm một danh sách số:

```java
// Cố ý không hợp lệ, đặt trong method trên:
groups.add(List.of(10, 20));
```

compiler không cho vì outer list yêu cầu `List<String>`, không phải `List<Integer>`.

**Ưu điểm:** Thiết kế đơn giản, generic type checking đầy đủ ở mã nguồn, thêm/bớt nhóm dễ dàng, không cần cast hay cảnh báo unchecked.

**Giới hạn:** Generic vẫn bị erasure tại runtime. Nếu dữ liệu đi qua raw type hoặc unchecked cast, vẫn có thể tạo heap pollution. Lợi thế là các thao tác thông thường trong code được kiểm tra generic không tạo ra đường đi array covariance gây xung đột.

## 11. Nếu số nhóm cố định thì sao?

Một số lý do người ta muốn dùng mảng là:

- Số slot cố định.
- Truy cập bằng chỉ số.
- Dùng API hiện có yêu cầu `Object[]` hoặc array.
- Cần một container có kích thước không đổi sau khởi tạo.

Để giữ kiểm tra kiểu mà không cần generic array creation, có thể dùng một `List<List<String>>` với cấu trúc ngoài không thể thay đổi:

```java
import java.util.List;

class FixedGroups {
    static List<List<String>> create() {
        return List.of(
                List.of("A", "B"),
                List.of("C")
        );
    }
}
```

Đây là class minh họa không có `main`. `List.of` trả các danh sách không cho sửa cấu trúc bằng API chuẩn. Điều này phù hợp với những nhóm dữ liệu ít thay đổi và không buộc bạn phải tạo mảng generic.

Nếu cần thay nội dung từng nhóm nhưng muốn giữ số lượng nhóm cố định, có thể dùng một outer list không sửa cấu trúc nhưng chứa các inner list có thể sửa, hoặc thiết kế object đại diện cho từng nhóm. Hãy phân biệt “số phần tử cố định”, “phần tử không đổi” và “nội dung collection bên trong không đổi”; chúng không đồng nghĩa.

### `List.copyOf` và kiểm tra dữ liệu

`List.copyOf(...)` tạo bản sao list không thể thay đổi qua API chuẩn và từ chối phần tử `null`. Nhưng như mọi generics Java thông thường, nó không “đọc lại” type argument runtime để xác nhận một object raw đang chứa đúng `String`. Nếu nguồn chưa tin cậy, cần kiểm tra dữ liệu thực tế trước khi xây cấu trúc.

## 12. Dùng `List<?>[]` khi chỉ cần các danh sách không biết phần tử

Trong một số API, ta thật sự cần mảng mà mỗi phần tử là một danh sách **không cần đồng nhất type argument**.

Khi đó:

```java
List<?>[] groups = new List<?>[3];
```

là một giải pháp có chủ ý. Nó mang ý nghĩa:

- Mảng có ba vị trí, mỗi vị trí có thể tham chiếu tới bất kỳ `List<?>` nào.
- Khi đọc `groups[i].get(j)`, kiểu an toàn là `Object` nếu không biết thêm thông tin.
- Không thể gọi `groups[i].add("hello")` tùy ý, bởi compiler không biết element type của inner list.
- Có thể thay cả slot bằng một danh sách khác, ví dụ `groups[0] = List.of("A")` rồi `groups[0] = List.of(1)`, vì cả hai đều là `List<?>`.

Nếu nghiệp vụ yêu cầu mỗi vị trí là `List<String>`, kiểu wildcard này **quá rộng**. Chọn container phù hợp với hợp đồng, đừng dùng `List<?>[]` và cast trở lại `List<String>[]` chỉ để compiler im lặng.

## 13. Type variable `T` cũng không là reifiable component type

```java
class GenericBuffer<T> {
    // T[] elements = new T[10]; // Lỗi generic array creation.
}
```

Một type variable `T` không trở thành runtime class cụ thể khi generic được tham số hóa. Nếu phải tạo `T[]`, hãy để caller truyền `IntFunction<T[]>` như `String[]::new`, hoặc token `Class<T>` để reflection tạo mảng đúng component. `(T[]) new Object[n]` không tương đương tạo `String[]`.

Trọng tâm ở đây vẫn là **mảng của `List<String>`**: ngay cả một factory cũng không hợp thức hóa `List<String>[]::new` do component non-reifiable. Việc thiết kế, kiểm tra length và null policy cho factory thuộc bài riêng về `IntFunction<T[]>` và `Class<T>`.

## 14. Reflection tạo mảng của `List`, không tạo runtime `List<String>`

`Array.newInstance(List.class, 2)` tạo một array có runtime component `java.util.List`. Nó có thể chứa `List.of("A")` và `List.of(123)` vì cả hai đều là `List`. Không có class literal `List<String>.class` để yêu cầu JVM kiểm tra đối số generic `String` ở mọi slot.

```java
Object array = java.lang.reflect.Array.newInstance(List.class, 2);
java.lang.reflect.Array.set(array, 0, List.of("A"));
java.lang.reflect.Array.set(array, 1, List.of(123));
System.out.println(array.getClass().getComponentType().getName());
// java.util.List
```

Chỉ dùng reflection/token để tạo **đúng runtime component class có thật**. Nếu nghiệp vụ đòi toàn bộ list con chứa chuỗi, kiểm tra dữ liệu/ownership và chọn `List<List<String>>` hoặc wrapper thay vì khẳng định mảng raw `List[]` bảo đảm `<String>`.

## 15. Liên hệ với generic varargs và cảnh báo heap pollution

Cú pháp varargs:

```java
static void receive(java.util.List<String>... groups) {
    // ...
}
```

có bề ngoài giống một tham số `List<String>[]`. Điều này không đồng nghĩa Java cho phép code của bạn gọi `new List<String>[n]`.

Tại lời gọi varargs, compiler có quy tắc sinh và sử dụng mảng cho tham số, bao gồm cảnh báo khi element type non-reifiable. Từ đó tồn tại nguy cơ **heap pollution** nếu method hoặc caller thao tác không an toàn qua mảng.

### Ví dụ không an toàn, chạy được nhưng có thể cảnh báo

Tệp **`UnsafeVarargsDemo.java`**:

```java
import java.util.List;

public class UnsafeVarargsDemo {

    static void unsafe(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);

        String text = groups[0].get(0);
        System.out.println(text);
    }

    public static void main(String[] args) {
        try {
            unsafe(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac UnsafeVarargsDemo.java
java UnsafeVarargsDemo
```

Stdout (không tính các cảnh báo biên dịch):

```text
ClassCastException
```

`javac` có thể in ghi chú cảnh báo generic/unchecked trong quá trình biên dịch; đó **không phải stdout của chương trình**. Để xem rõ các cảnh báo:

```bash
javac -Xlint:unchecked -Xlint:varargs UnsafeVarargsDemo.java
```

Phân tích:

- Varargs parameter được triển khai thông qua array.
- `Object[] alias = groups` hợp lệ do array covariance.
- `alias[0] = List.of(99)` lưu một `List<Integer>` vào slot mà mã nguồn method kỳ vọng là `List<String>`.
- Runtime component chỉ có thể biết `List`, nên không chặn kiểu phần tử `Integer`.
- Khi `groups[0].get(0)` được dùng như `String`, phép cast thất bại.

Đừng dùng `@SafeVarargs` để tắt cảnh báo trong method **không an toàn** này. Annotation đó là lời cam kết của người viết rằng triển khai thực sự không có thao tác gây heap pollution trên varargs parameter.

## 16. Khi nào `@SafeVarargs` phù hợp?

Một method generic varargs có thể an toàn nếu nó **không ghi sai kiểu vào array varargs**, không công khai/thả tham chiếu tới array cho nơi khác có thể sửa không an toàn, và dùng dữ liệu theo hợp đồng.

Ví dụ **`SafeVarargsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {

    @SafeVarargs
    static <T> List<T> flatten(List<? extends T>... batches) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> batch : batches) {
            result.addAll(batch);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words = flatten(
                List.of("A"), List.of("B", "C"));

        System.out.println(words);
        System.out.println(words.size());
    }
}
```

Biên dịch/chạy:

```bash
javac SafeVarargsDemo.java
java SafeVarargsDemo
```

Stdout:

```text
[A, B, C]
3
```

Ở đây `flatten` chỉ đọc từng list để tạo một `ArrayList<T>` mới, không gán phần tử sai vào mảng varargs và không tiết lộ array để nơi khác chỉnh sửa. `List.copyOf` trả về danh sách không cho sửa cấu trúc qua API chuẩn.

`@SafeVarargs` có những ràng buộc về vị trí được áp dụng: ví dụ Java 17 cho phép trên constructor và method static/final, cũng như private instance methods theo những điều kiện ngôn ngữ quy định. **Nó không thể được gắn tùy tiện lên bất kỳ method nào**, và người viết chịu trách nhiệm đảm bảo triển khai thật sự an toàn.

**Không dùng annotation như mẹo để hợp thức hóa `new List<String>[]`.** Nó phục vụ một ngữ cảnh riêng: lời hứa về an toàn của việc sử dụng generic varargs.

## 17. Dùng mảng thường của wrapper thay vì mảng của kiểu tham số hóa

Nếu chương trình thực sự cần hiệu năng truy cập theo chỉ số hoặc tương tác với API yêu cầu array, một cách thiết kế rõ hơn là dùng **một loại wrapper không tham số hóa với thành phần runtime reifiable**.

Ví dụ cần các nhóm chuỗi có số slot cố định. Tạo tệp **`GroupWrapperArrayDemo.java`**:

```java
import java.util.List;

public class GroupWrapperArrayDemo {

    record StringGroup(List<String> elements) {
        StringGroup {
            elements = List.copyOf(elements);
        }
    }

    public static void main(String[] args) {
        StringGroup[] groups = new StringGroup[2];

        groups[0] = new StringGroup(List.of("A", "B"));
        groups[1] = new StringGroup(List.of("C"));

        System.out.println(groups.length);
        System.out.println(groups[0].elements().get(1));
        System.out.println(groups.getClass()
                .getComponentType().getSimpleName());
    }
}
```

Biên dịch/chạy:

```bash
javac GroupWrapperArrayDemo.java
java GroupWrapperArrayDemo
```

Stdout:

```text
2
B
StringGroup
```

`StringGroup` là một record có **class runtime cụ thể**. JVM có thể tạo và kiểm tra mảng `StringGroup[]`. Bên trong wrapper, `List<String>` vẫn được compiler kiểm tra theo generic contract.

Đây không phải cách tự động xóa mọi rủi ro: raw/unchecked access vẫn có thể làm hỏng dữ liệu nếu thiết kế có lỗ hổng. Tuy vậy, wrapper tách bạch ý nghĩa nghiệp vụ và tránh nhu cầu tạo mảng với một parameterized component type bị cấm.

### Khi nào nên chọn wrapper?

- Mỗi phần tử array đại diện một khái niệm nghiệp vụ độc lập, không chỉ là một list bất kỳ.
- Cần đặt validation/copy dữ liệu ở điểm tạo object.
- API bắt buộc nhận array và muốn runtime component class cụ thể.
- Muốn code dễ đọc hơn một unchecked cast trên `List<String>[]`.

Với phần lớn ứng dụng thuần collection, `List<List<String>>` vẫn đơn giản hơn.

## 18. So sánh toàn diện các cách tổ chức dữ liệu

| Thiết kế | Tạo trực tiếp? | Kiểm tra generic ở mã nguồn | Runtime component check |
|---|---|---|---|
| `String[]` | Có | Không cần tham số generic | Kiểm tra `String` |
| `List<String>[]` với `new List<String>[n]` | **Không** | Khai báo mong `List<String>` | Không thể kiểm tra `<String>` ở array store |
| `List<?>[]` với `new List<?>[n]` | Có | Wildcard giữ hạn chế generic khi truy cập inner list | Chỉ kiểm tra đối tượng là `List` |
| Raw `List[]` | Có, không khuyến khích cho code mới | Mất kiểm tra type argument ở đường raw | Kiểm tra raw `List` |
| `List<List<String>>` | Có | Kiểm tra cả hai cấp khi dùng typed API | Không dùng array store checks |
| `StringGroup[]` với wrapper không generic | Có | Inner `List<String>` được kiểm tra ở code thông thường | Kiểm tra `StringGroup` |

Chọn theo yêu cầu thật:

1. **Cần tập các danh sách đồng nhất chuỗi?** Dùng `List<List<String>>`.
2. **Cần mảng của các danh sách bất kỳ?** Dùng `List<?>[]` và chấp nhận kiểu phần tử chưa biết.
3. **Cần array runtime với loại nghiệp vụ cụ thể?** Cân nhắc một wrapper/record không tham số hóa.
4. **Cần `T[]` trong generic utility?** Truyền factory hoặc class token cho component type reifiable.
5. **Đang xử lý API legacy buộc dùng cast?** Khoanh vùng unchecked operation, kiểm tra nguồn dữ liệu và ghi rõ invariant. Không coi cast là phép kiểm tra generic runtime.

## 19. Những sai lầm phổ biến

**Sai lầm 1 — “Không thể khai báo biến `List<String>[]`.”** Sai. Có thể khai báo kiểu biến này. Điều bị cấm là *trực tiếp tạo* mảng `new List<String>[n]` với component type non-reifiable.

**Sai lầm 2 — “Java cấm mọi mảng có kiểu generic.”** Sai. `List<?>[]` là ví dụ hợp lệ vì wildcard không giới hạn giúp component type reifiable theo đặc tả.

**Sai lầm 3 — “Nếu `List<String>` và `List<Integer>` khác nhau ở compile time, JVM chắc chắn kiểm tra được ở array store.”** Sai. Kiểu phần tử generic đã bị xóa ở runtime; mảng chỉ kiểm tra raw `List`.

**Sai lầm 4 — “`new List[n]` giải quyết đầy đủ vấn đề.”** Sai. Raw `List[]` có thể tạo được, nhưng không đảm bảo `String` và có thể dẫn tới unchecked warnings, heap pollution.

**Sai lầm 5 — “`@SuppressWarnings("unchecked")` biến cast thành an toàn.”** Sai. Annotation chỉ kiểm soát cảnh báo biên dịch; nó không thêm runtime generic type checks.

**Sai lầm 6 — “`List<?>[]` tương đương `List<String>[]`.”** Sai. Mỗi slot `List<?>` có thể nhận một danh sách với bất kỳ type argument nào; không có cam kết `String`.

**Sai lầm 7 — “Mảng của `List<?>` không còn runtime type checking.”** Sai. Runtime vẫn kiểm tra được một object có phải `List` hay không; nó chỉ không kiểm tra type argument của mỗi list.

**Sai lầm 8 — “`ArrayStoreException` và `ClassCastException` luôn xuất hiện tại cùng vị trí.”** Sai. Store check của mảng reifiable có thể báo lỗi **lúc gán**; generic heap pollution thường bộc lộ **lúc đọc/cast**.

**Sai lầm 9 — “`new T[n]` hợp lệ khi `T extends Number`.”** Sai. `T` vẫn là type variable, không phải class component reifiable trong array creation trực tiếp.

**Sai lầm 10 — “Reflection có thể tạo `List<String>[]` bằng `List<String>.class`.”** Sai. `List<String>.class` không tồn tại; `Array.newInstance(List.class,n)` chỉ dùng component raw `List`.

**Sai lầm 11 — “Varargs `List<String>...` luôn an toàn vì compiler tự tạo array.”** Sai. Generic varargs có thể tạo heap pollution nếu method gán sai kiểu hoặc làm lộ array.

**Sai lầm 12 — “`@SafeVarargs` chỉ cần thêm để tắt warning.”** Sai. Đây là cam kết an toàn của người viết method và không được dùng cho một thân method gây heap pollution.

**Sai lầm 13 — “Array covariance và generic invariance mâu thuẫn hoàn toàn.”** Không. Đây là hai quy tắc được thiết kế cho các cơ chế khác nhau. Mảng bảo vệ thao tác store thông qua runtime component checks, còn invariance góp phần giữ an toàn generic ở compile time.

**Sai lầm 14 — “Wrapper hoặc `List<List<String>>` làm generics trở thành reified.”** Không. Chúng đưa ra cấu trúc dữ liệu và hợp đồng an toàn dễ quản lý hơn, không đổi cơ chế type erasure chung của Java.

## 20. Bài tập tự kiểm tra có đáp án

**Câu 1.** Dòng nào hợp lệ?

```java
List<String>[] a;              // A
List<String>[] b = new List<String>[2]; // B
List<?>[] c = new List<?>[2];  // C
```

**Đáp án:** A và C hợp lệ; B lỗi `generic array creation`. Giả sử import `java.util.List` và đặt trong một ngữ cảnh khai báo tương ứng.

**Câu 2.** Vì sao `String[]` có thể bị `ArrayStoreException` khi gán `Integer` qua `Object[]`?

**Đáp án:** Object mảng có component type runtime `String`, nên JVM kiểm tra và từ chối `Integer` tại thời điểm store.

**Câu 3.** Vì sao object `List.of(42)` được lưu vào `Object[]` alias của một `List<?>[]` mà không gây `ArrayStoreException`?

**Đáp án:** Runtime component type chỉ là `java.util.List`; `List.of(42)` tạo object triển khai `List`, phù hợp raw runtime type. JVM không so sánh generic type argument của mỗi list.

**Câu 4.** Có thể ép `(List<String>[]) new List<?>[2]` không?

**Đáp án:** Có thể xuất hiện unchecked cast theo compiler, nhưng nó **không chứng minh** những slot chứa `List<String>`. Không dùng nó như một bảo đảm an toàn kiểu.

**Câu 5.** Dùng cấu trúc gì cho một tập động các danh sách chuỗi?

**Đáp án:** `List<List<String>>` thường là lựa chọn trực tiếp, dễ bảo trì và được compiler kiểm tra ở cả hai cấp trong code có kiểu rõ ràng.

**Câu 6.** Có thể trực tiếp `new T[10]` bên trong `class Bucket<T>` không?

**Đáp án:** Không, vì type variable `T` không phải runtime component class reifiable. Một array factory `IntFunction<T[]>` có thể cho phép caller cung cấp constructor reference của kiểu component thật.

**Câu 7.** `@SafeVarargs` có thể đặt lên method ghi `List<Integer>` vào array of `List<String>` rồi coi là an toàn không?

**Đáp án:** Không. Đó là hành vi tạo heap pollution. Annotation phải phản ánh sự an toàn thật của triển khai.

**Câu 8.** Một biến `List<?>[]` có thể chứa `List<String>` ở slot 0 và `List<Integer>` ở slot 1 không?

**Đáp án:** Có. Wildcard biểu diễn type argument chưa biết ở từng list.

**Câu 9.** `List<String>[]` và `List<?>[]` có cùng runtime component class sau erasure không?

**Đáp án:** Nếu một object array được tạo qua raw/wildcard component và một reference `List<String>[]` trỏ đến nó bằng unchecked operation, runtime component class vẫn là `List`. Điều này chính là giới hạn mà compiler ngăn khi cấm trực tiếp generic array creation.

**Câu 10.** `List<String>[]::new` có dùng làm factory cho generic array trong Java 17 không?

**Đáp án:** Không. Nó vẫn đòi tạo array có component type `List<String>` non-reifiable; hãy dùng kiểu dữ liệu khác thay vì kỳ vọng constructor reference bỏ qua quy tắc array creation.

## 21. Thực hành tổng hợp: lựa chọn giải pháp trước khi viết code

**Tình huống A — Một lớp học có nhiều nhóm, mỗi nhóm có danh sách tên học viên.** Chọn `List<List<String>>`. Khi thêm nhóm hoặc tên, compiler có thể chặn việc đưa `Integer` vào danh sách tên.

**Tình huống B — Công cụ nhận nhiều loại list và chỉ muốn thống kê số phần tử từng list.** `List<?>[]` có thể phù hợp nếu API thật sự cần mảng; khi duyệt, đọc phần tử như `Object` và không giả định kiểu cụ thể.

**Tình huống C — Một thư viện yêu cầu `StringGroup[]` vì cần mảng object có component class xác định.** Tạo record/class `StringGroup` mang `List<String>` bên trong; runtime kiểm tra được `StringGroup` khi thay phần tử mảng.

**Tình huống D — Một generic helper cần cấp phát `T[]` với `T` chưa biết trước.** Truyền `IntFunction<T[]>` hoặc `Class<T>` phù hợp. Khi type argument không reifiable, hãy đánh giá lại cấu trúc thay vì cast unchecked một mảng raw rồi kỳ vọng JVM biết đối số generic.

**Tình huống E — Một API legacy trả `Object[]` hoặc raw array và caller muốn `List<String>[]`.** Cần hiểu dữ liệu nguồn, kiểm tra từng đối tượng và từng phần tử nếu cần chứng minh hợp đồng. Dùng một collection typed mới thường tốt hơn ép nguyên array với unchecked cast.

### Quy trình quyết định

1. Bạn **có thật sự cần mảng** hay chỉ cần một collection có khả năng truy cập chỉ số?
2. Nếu cần mảng, **component type có reifiable không**?
3. Nếu muốn `List<String>[]`, bạn có thể thay bằng `List<List<String>>` không?
4. Nếu bắt buộc tương thích API nhận array, `List<?>[]` có phản ánh đúng hợp đồng **không biết kiểu phần tử** không?
5. Nếu cần đồng nhất `String`, có thể dùng wrapper reifiable hoặc một API generic không dựa trên generic array creation không?
6. Có đoạn raw/unchecked nào làm mất chứng minh kiểu không, và ranh giới kiểm tra dữ liệu ở đâu?

Chỉ dùng giải pháp có unchecked cast nếu không có một hợp đồng khác đơn giản hơn và bạn kiểm soát toàn bộ dữ liệu liên quan.

## 22. Tổng kết và nguồn chuẩn

**Không thể trực tiếp tạo `new List<String>[]` vì `List<String>` là non-reifiable type**, trong khi Java yêu cầu component type của biểu thức tạo mảng phải reifiable. Java arrays là covariant và có runtime store checks; Java Generics dùng type erasure, nên runtime mảng không thể phân biệt đầy đủ `List<String>` với `List<Integer>`. Cho phép tạo mảng đó trực tiếp sẽ khiến compiler cấp một cam kết kiểu mà JVM không thể xác minh khi các tham chiếu rộng hơn được sử dụng.

Có thể **khai báo** biến `List<String>[]`, nhưng tạo trực tiếp `new List<String>[n]` bị cấm. `new List<?>[n]` được phép vì wildcard không giới hạn là reifiable, song không hứa rằng mọi list đều chứa String. Một unchecked cast có thể tạo nguy cơ heap pollution và `ClassCastException` về sau.

Trong code mới, **`List<List<String>>` là lựa chọn mặc định tốt** cho một tập các danh sách chuỗi. Khi thật sự cần array, chọn component type reifiable (`StringGroup[]`) hoặc wildcard phù hợp với hợp đồng, thay vì tắt cảnh báo để ép kiểu không được xác minh.

Tài liệu tham khảo:

- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): định nghĩa loại kiểu có đủ thông tin runtime.
- [Java Language Specification §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): runtime array store checks.
- [Java Language Specification §15.10.1 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): giới hạn component type của biểu thức tạo mảng.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): cách tính kiểu sau xóa.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): quan hệ và kiểm tra parameterized types.
- [Java Language Specification §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): yêu cầu đối với annotation an toàn varargs.
- [Java SE 17 `java.util.Collections`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): tiện ích collections dùng trong các lựa chọn thay thế.