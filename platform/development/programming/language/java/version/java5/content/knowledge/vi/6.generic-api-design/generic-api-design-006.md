# Thiết kế vùng lưu trữ phân biệt dữ liệu bằng Class<T>

## 1. Bài toán: nhiều loại giá trị trong cùng một vùng lưu trữ

Một `Map<String, Object>` có thể chứa nhiều loại dữ liệu, nhưng nơi đọc thường phải tự ghi nhớ kiểu của từng khóa:

```java
String title = (String) values.get("title");
Integer version = (Integer) values.get("version");
```

Đây là đoạn minh họa, giả sử `values` là một map đã có dữ liệu. Chữ ký của map không nối khóa chuỗi với kiểu kết quả; một phép ghi sai có thể làm cast thất bại lúc chạy.

Nếu bài toán cần **mỗi kiểu lớp có một giá trị**, có thể dùng chính đối tượng `Class<T>` làm khóa:

```java
TypeStore store = new TypeStore();
store.put(String.class, "Java");
store.put(Integer.class, 21);

String title = store.find(String.class).orElseThrow();
Integer version = store.find(Integer.class).orElseThrow();
```

Khóa `String.class` vừa nhận diện ô lưu trữ vừa giữ quan hệ với kết quả `String`. Nơi gọi không cần viết cast.

Mẫu này thường được gọi là vùng chứa nhiều kiểu có kiểm tra kiểu (typesafe heterogeneous container). Lớp chứa không có một tham số kiểu cố định cho toàn bộ dữ liệu; mỗi lời gọi `put` hoặc `find` có tham số kiểu riêng.

Các quy tắc và API trong bài vẫn áp dụng trên Java hiện đại. Chương trình đầy đủ chạy bằng Java 17+.

## 2. Class<T> mang thông tin gì?

`Class<T>` là một đối tượng mô tả một lớp hoặc interface lúc chạy, có tham số kiểu nối với kiểu được mô tả:

| Biểu thức | Kiểu tại thời điểm biên dịch |
| --- | --- |
| `String.class` | `Class<String>` |
| `Integer.class` | `Class<Integer>` |
| `Number.class` | `Class<Number>` |
| `CharSequence.class` | `Class<CharSequence>` |
| `String[].class` | `Class<String[]>` |

Một đối tượng mô tả kiểu được truyền tường minh như vậy thường được gọi là thẻ kiểu (type token).

Chữ ký:

```java
<T> void put(Class<T> type, T value)
```

nói rằng giá trị phải dùng được như kiểu mà khóa lớp mô tả. Chữ ký:

```java
<T> Optional<T> find(Class<T> type)
```

nối kiểu khóa được yêu cầu với kiểu phần tử của kết quả.

Hai dòng trên là chữ ký để thảo luận; phần cài đặt đầy đủ ở mục 5.

### 2.1. T được chọn theo từng lời gọi

```java
store.put(String.class, "Java"); // T = String.
store.put(Integer.class, 21);    // T = Integer, giá trị được boxing.
```

Đây không phải một `TypeStore<Object>` mà nơi đọc phải cast thủ công. Cũng không phải một `TypeStore<T>` chỉ chứa một kiểu cho mọi khóa.

Nếu khai báo lớp `class TypeStore<T>` rồi dùng `Map<Class<T>, T>`, ta đã cố định một `T` cho một thể hiện, làm mất mục tiêu chứa nhiều loại dữ liệu trong cùng vùng lưu trữ.

## 3. Biểu diễn nội bộ và bất biến cần bảo vệ

Có thể dùng:

```java
private final Map<Class<?>, Object> entries = new HashMap<>();
```

- `Class<?>` cho phép các khóa lớp khác nhau.
- `Object` cho phép các giá trị thuộc các kiểu tham chiếu khác nhau.
- Nhưng bản thân kiểu map chưa diễn đạt rằng mỗi giá trị phải phù hợp với lớp tại chính khóa của nó.

Bất biến của vùng lưu trữ là:

> Với mỗi cặp khóa–giá trị được giữ trong map, đối tượng giá trị phải là một thể hiện hợp lệ của kiểu mà khóa lớp mô tả.

Cần giữ map private và cho mọi đường ghi đi qua API bảo vệ bất biến đó. Nếu trả map có thể sửa cho bên ngoài, toàn bộ hợp đồng của `find` có thể bị phá vỡ.

### 3.1. Class.cast khôi phục quan hệ tại ranh giới đọc

```java
Object value = entries.get(type);
T result = type.cast(value);
```

Đoạn minh họa giả sử đang ở trong phương thức có tham số `Class<T> type`.

`type.cast` kiểm tra lớp thực tế của đối tượng theo thẻ kiểu rồi trả về `T`. Nếu đối tượng không phù hợp, nó ném `ClassCastException`. Nó không tạo hoặc chuyển đổi dữ liệu thành một đối tượng mới.

Đây khác với viết `(T) value`: một cast sang biến kiểu không được kiểm tra không mang đầy đủ lớp thực thi của `T`. `Class<T>` là đối số bổ sung cung cấp thông tin lớp thật để kiểm tra.

`Class.cast(null)` trả `null`. Bài này chọn cấm lưu giá trị `null`, để `Optional.empty()` khi đọc chỉ có nghĩa không có ánh xạ.

### 3.2. Kiểm tra cả khi ghi

Dù chữ ký `put(Class<T>, T)` đã giúp mã nguồn có kiểm tra kiểu truyền đúng dữ liệu, ta vẫn có thể gọi `type.cast(value)` trước khi lưu. Như vậy mọi đường ghi của phần cài đặt này đều thể hiện rõ cùng một kiểm tra runtime.

Không cần `@SuppressWarnings("unchecked")` và không cần để cast ở nơi sử dụng.

Nếu cố tình đi vòng qua kiểm tra generics bằng raw type, trình biên dịch có thể phát cảnh báo; kiểm tra `Class.cast` tại đường ghi vẫn giúp phát hiện đối tượng sai lớp ở ranh giới. Đó là lý do giữ kiểm tra này, không phải lý do sử dụng raw type.

## 4. Chọn hợp đồng rõ ràng trước khi cài đặt

Vùng lưu trữ trong bài có các quy tắc:

1. Mỗi khóa lớp lưu tối đa một giá trị.
2. Ghi lại cùng khóa sẽ thay thế giá trị trước đó.
3. Khóa và giá trị phải khác `null`.
4. Chỉ chấp nhận thẻ kiểu tham chiếu; từ chối thẻ kiểu nguyên thủy và `void.class`.
5. Tìm theo **đúng khóa lớp**, không tự tìm qua các lớp con.
6. Không tạo bản sao sâu của giá trị.
7. Không cung cấp bảo đảm truy cập đồng thời.

Những quyết định này không phải do generics tự áp đặt. Chúng là hợp đồng cụ thể của API đang thiết kế.

### 4.1. Một đối tượng lớp không nhất thiết là một lớp có thể new

Vùng lưu trữ chỉ nhận đối tượng đã tồn tại; không gọi hàm tạo của lớp. Vì vậy, khóa có thể là một interface hoặc một lớp trừu tượng:

```java
store.put(CharSequence.class, new StringBuilder("draft"));
store.put(Number.class, 3.5);
```

Giá trị lần lượt dùng được như `CharSequence` và `Number`. Không cần tạo trực tiếp một `CharSequence` hoặc gọi `new Number()`.

### 4.2. Khóa là kiểu yêu cầu, không tự động là lớp thực tế

Một `Integer` có thể được lưu dưới khóa `Number.class` nếu đó là hợp đồng mà nơi gọi chọn:

```java
store.put(Number.class, 21);
Number number = store.find(Number.class).orElseThrow();
```

Ở đây `T = Number`; kiểu thực tế của giá trị có thể là `Integer`. “Phù hợp với kiểu khóa” không có nghĩa “lớp thực tế phải bằng chính khóa”.

## 5. Chương trình hoàn chỉnh

Lưu thành `ClassStoreDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class ClassStoreDemo {
    static final class TypeStore {
        private final Map<Class<?>, Object> entries = new HashMap<>();

        private static <T> Class<T> referenceType(Class<T> type) {
            Objects.requireNonNull(type, "type");
            if (type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Use reference type tokens");
            }
            return type;
        }

        <T> void put(Class<T> type, T value) {
            Class<T> checkedType = referenceType(type);
            Objects.requireNonNull(value, "value");
            entries.put(checkedType, checkedType.cast(value));
        }

        <T> Optional<T> find(Class<T> type) {
            Class<T> checkedType = referenceType(type);
            Object value = entries.get(checkedType);
            return Optional.ofNullable(checkedType.cast(value));
        }
    }

    public static void main(String[] args) {
        TypeStore store = new TypeStore();
        store.put(String.class, "Java");
        store.put(Integer.class, 21);

        String title = store.find(String.class).orElseThrow();
        Integer version = store.find(Integer.class).orElseThrow();

        System.out.println("title = " + title);
        System.out.println("version = " + version);
        System.out.println("number before = "
                + store.find(Number.class).isPresent());

        store.put(Number.class, 3.5);
        Number number = store.find(Number.class).orElseThrow();
        System.out.println("number after = " + number);

        store.put(String.class, "Java Learning");
        System.out.println("updated title = "
                + store.find(String.class).orElseThrow());
        System.out.println("missing boolean = "
                + store.find(Boolean.class).isEmpty());

        try {
            store.put(int.class, 7);
        } catch (IllegalArgumentException failure) {
            System.out.println("primitive token = rejected");
        }

        // Không biên dịch nếu bật các dòng sau:
        // store.put(Integer.class, "twenty-one");
        // String wrong = store.find(Integer.class).orElseThrow();
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all ClassStoreDemo.java
java ClassStoreDemo
```

Stdout chính xác:

```text
title = Java
version = 21
number before = false
number after = 3.5
updated title = Java Learning
missing boolean = true
primitive token = rejected
```

Các dòng output kiểm chứng những khía cạnh khác nhau:

- Hai loại giá trị được đọc ra bằng đúng kiểu mà khóa yêu cầu.
- Có khóa `Integer.class` không làm khóa `Number.class` tự tồn tại.
- Ghi `Number.class` tạo ánh xạ riêng.
- Ghi lần hai vào `String.class` thay thế giá trị.
- Không có khóa `Boolean.class` thì kết quả rỗng.
- Thẻ kiểu nguyên thủy bị chặn theo hợp đồng đã công bố.

Hai dòng sai kiểu ở cuối bị đánh dấu rõ. Dòng đầu không thỏa cùng một `T` cho `Class<Integer>` và chuỗi; dòng sau cố nhận một `Integer` bằng biến `String`.

## 6. Các trường hợp biên cần hiểu đúng

### 6.1. Tra cứu chính xác khác với tìm theo quan hệ kế thừa

```java
store.put(Integer.class, 21);
Optional<Number> result = store.find(Number.class);
```

Với một store mới chỉ có ánh xạ đó, `result` rỗng. Map tra đúng khóa, không duyệt toàn bộ để tìm một giá trị có thể dùng như `Number`.

Nếu muốn hỗ trợ tra theo kiểu cha, cần một API khác và quy tắc giải quyết xung đột. Ví dụ có cả giá trị `Integer` và `Double` thì yêu cầu `Number` chọn cái nào? Không nên tự thêm kiểu tra cứu đa hình khi hợp đồng chỉ định khóa chính xác.

### 6.2. int.class không phải Integer.class

Điểm dễ bất ngờ là kiểu của biểu thức `int.class` trong mã nguồn là `Class<Integer>`, nhưng đối tượng lớp đó vẫn mô tả **kiểu nguyên thủy int**. Nó khác `Integer.class`.

`Class.cast` của thẻ kiểu nguyên thủy không thực hiện unboxing để nhận một đối tượng wrapper như `Integer`. Vì thế, chữ ký `Class<T>` một mình chưa đủ để tránh trường hợp này.

Hàm `referenceType` dùng `isPrimitive()` để từ chối các thẻ kiểu nguyên thủy, bao gồm `void.class`. Nơi gọi muốn lưu số nguyên hãy dùng `Integer.class`.

Một API khác có thể chọn chuẩn hóa thẻ kiểu nguyên thủy thành wrapper, nhưng phải định nghĩa cách chuẩn hóa nhất quán cho cả đọc lẫn ghi. Bài này chọn quy tắc từ chối để giữ hợp đồng đơn giản.

### 6.3. Giá trị mutable vẫn được chia sẻ

```java
StringBuilder draft = new StringBuilder("a");
store.put(CharSequence.class, draft);
draft.append("b");

CharSequence value = store.find(CharSequence.class).orElseThrow();
System.out.println(value); // ab
```

Vùng lưu trữ giữ tham chiếu đến đối tượng. Nó không sao chép sâu hoặc biến `StringBuilder` thành bất biến. Nếu cần cách ly trạng thái, phải bổ sung hợp đồng sao chép hoặc dùng giá trị bất biến phù hợp.

### 6.4. Class<?> làm khóa vẫn phân biệt danh tính lớp

Không nên thay khóa bằng `type.getName()` rồi giả định tương đương. Hai lớp có cùng tên nhị phân nhưng được định nghĩa bởi các class loader khác nhau có thể là các kiểu khác nhau lúc chạy.

Giữ chính đối tượng `Class` làm khóa bảo toàn cách Java nhận diện kiểu thực thi. Với môi trường nạp plugin hoặc lớp động, cũng cần cân nhắc vòng đời vùng lưu trữ vì các khóa và giá trị có thể giữ tham chiếu đến lớp và class loader.

## 7. Giới hạn quan trọng: không mô tả được mọi kiểu có tham số

Không có class literal:

```java
// Không hợp lệ:
// List<String>.class
```

`List.class` chỉ mô tả lớp/interface `List`; nó không mang riêng đối số kiểu `String` hay `Integer`. Do đó, mẫu dùng một `Class` làm khóa không phân biệt trực tiếp hai ô:

```text
List<String>
List<Integer>
```

`Class.cast` cũng không duyệt toàn bộ danh sách để kiểm tra kiểu từng phần tử. Nó kiểm tra sự phù hợp với lớp hoặc interface mà thẻ kiểu mô tả.

Nếu cần nhận diện kiểu có tham số đầy đủ, phải có mô hình mô tả kiểu phong phú hơn và quy tắc xác thực dữ liệu tương ứng. Việc giữ một `java.lang.reflect.Type` hoặc một đối tượng mô tả kiểu không tự động bảo đảm mọi phần tử bên trong dữ liệu động đúng kiểu; cần kiểm soát cách dữ liệu được tạo, ghi và giải mã.

Đừng chuyển `List.class` thành một `Class<List<String>>` bằng cast không được kiểm tra để giả lập thông tin không tồn tại.

## 8. Khi một lớp cần nhiều giá trị khác nhau

Mẫu trong bài phù hợp với một giá trị trên mỗi kiểu. Nó không đủ để phân biệt hai chuỗi như `host` và `username`:

```java
store.put(String.class, "example.test");
store.put(String.class, "alice");
```

Lời gọi thứ hai thay thế lời gọi thứ nhất. Đây là hành vi theo thiết kế.

Các hướng phù hợp tùy bài toán:

- Dùng kiểu nghiệp vụ khác nhau, chẳng hạn cấu hình kết nối và thông tin người dùng.
- Dùng khóa có định danh riêng kèm kiểu, ví dụ một mô hình `Key<T>`.
- Dùng một cấu trúc có tên trường rõ ràng nếu tập dữ liệu ổn định và đã biết trước.

Không cần tạo một vùng lưu trữ tổng quát cho mọi nhóm trường dữ liệu. Một lớp cấu hình hoặc record có tên thành phần rõ ràng thường dễ hiểu hơn khi cấu trúc không thay đổi.

Nếu chọn `Key<T>`, cần thiết kế lại bất biến và cách xác thực của nó; không thể coi việc bỏ `Class<T>` là vẫn tự giữ nguyên khả năng kiểm tra của `Class.cast`.

## 9. Ownership, mở rộng và truy cập đồng thời

Phần cài đặt dùng `HashMap`, nên không tự an toàn khi nhiều luồng cùng đọc/ghi. Generics và `Class.cast` kiểm soát quan hệ kiểu, không cung cấp đồng bộ hóa.

Nếu cần mở rộng, hãy giữ các nguyên tắc:

1. Mọi đường thêm hoặc thay thế dữ liệu phải bảo vệ cùng bất biến khóa–giá trị.
2. Không để bên ngoài sửa map nội bộ.
3. Thao tác xóa nên giữ quan hệ với khóa, chẳng hạn `<T> Optional<T> remove(Class<T> type)`.
4. Thao tác “tìm hoặc tạo” cần hợp đồng về cạnh tranh, số lần gọi factory và khả năng tạo trùng; đổi sang map đồng thời không tự giải quyết mọi chuỗi thao tác.
5. Chính sách vòng đời của dịch vụ hoặc tài nguyên được lưu phải tách khỏi việc kiểm tra kiểu.

Nếu mục đích là ghi nhận một vài đối tượng dịch vụ đã tạo, mẫu nhỏ này có thể đủ. Nếu cần khởi tạo phụ thuộc, quản lý tài nguyên, phạm vi sống và xử lý vòng phụ thuộc, đó là trách nhiệm bổ sung của một hệ thống quản lý thành phần.

## 10. Cách tự đánh giá một thiết kế Class<T>

Một thiết kế có thể giải thích rõ:

- `Class<T>` ở đầu vào nối với `T` ở giá trị hoặc kết quả.
- Cấu trúc nội bộ chưa tự chứng minh quan hệ từng cặp; phần cài đặt đóng kín bảo vệ nó.
- `Class.cast` kiểm tra kiểu thật tại ranh giới, không chỉ che cảnh báo.
- Khóa chính xác, ghi đè, vắng mặt, `null` và thẻ kiểu nguyên thủy đều có quy tắc.
- Kiểu có tham số lồng nhau, nhiều giá trị cùng lớp và truy cập đồng thời có giới hạn rõ ràng.

Khi các điều đó được xác định, nơi gọi có thể đọc đúng kiểu bằng khóa lớp và để vùng lưu trữ chịu trách nhiệm duy trì quan hệ kiểu.

## Tài liệu đối chiếu

- [Java Class API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `Class<T>`, `cast`, `isPrimitive` và thông tin lớp lúc chạy.
- [JLS §15.8.2 — Class Literals](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.8.2): kiểu của các biểu thức như `String.class` và `int.class`.
- [Java Map API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): ánh xạ theo khóa và hành vi ghi đè.
