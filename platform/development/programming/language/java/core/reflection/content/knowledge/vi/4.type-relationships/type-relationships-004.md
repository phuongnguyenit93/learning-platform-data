# Duyệt đồ thị interface và tránh lặp bằng Java Reflection

## 1. Mục tiêu và bài toán

Khi dùng Reflection, một lớp Java có thể triển khai nhiều interface; mỗi interface lại có thể mở rộng nhiều interface khác. Ngoài ra, lớp còn kế thừa interface gián tiếp qua các lớp cha. Vì thế, gọi `getInterfaces()` một lần thường **chưa đủ** nếu muốn tìm **tất cả interface mà một kiểu có quan hệ kế thừa/triển khai**.

Sau bài này, bạn có thể:

- Phân biệt interface trực tiếp với interface kế thừa gián tiếp qua `extends` và `implements`.
- Xây thuật toán duyệt đồ thị interface bằng `Class<?>`, `getInterfaces()` và `getSuperclass()`.
- Dùng tập `visited` để mỗi interface chỉ xuất hiện một lần, kể cả khi có cấu trúc hình thoi.
- Chọn thứ tự duyệt phù hợp và hiểu các ngoại lệ: đầu vào là interface, lớp, kiểu mảng hoặc kiểu nguyên thủy.
- Phân biệt **liệt kê** interface với **kiểm tra** quan hệ kiểu bằng `isAssignableFrom()`.

Ở đây, “tất cả interface” có nghĩa: **các interface tổ tiên** của kiểu đầu vào; nếu đầu vào chính là một interface, **không tính interface đầu vào vào danh sách kết quả**. Định nghĩa này quyết định cách khởi tạo thuật toán.

## 2. Mô hình đồ thị: vì sao cần duyệt?

Xem khai báo sau:

```java
interface Root {}
interface Left extends Root {}
interface Right extends Root {}
interface Diamond extends Left, Right {}

class Base implements Left {}
class Child extends Base implements Diamond, Right {}
```

Các quan hệ chính:

```text
                  Child
                 /     \
       implements       extends
        /        \          \
    Diamond     Right       Base
     /   \        |           |
   Left  Right   Root         Left
     \     /                    |
       Root                    Root
```

Sơ đồ biểu diễn nhiều đường có thể dẫn đến cùng một interface; đây là **đồ thị có hướng**, không phải cây. Chẳng hạn, `Root` có thể được tìm thấy qua `Diamond → Left → Root`, `Diamond → Right → Root` hoặc `Base → Left → Root`. Nếu chỉ ghép các kết quả đệ quy mà không ghi nhớ nút đã gặp, `Left`, `Right` và `Root` có thể bị liệt kê nhiều lần.

Trong mã Java hợp lệ, một interface không thể tạo chu trình kế thừa `A extends B` rồi `B extends A`. Dù vậy, `visited` vẫn cần thiết để xử lý **nhiều đường tới cùng một nút**; tính đúng đắn của thuật toán không dựa vào giả định “mọi nút chỉ xuất hiện trên một đường đi”.

## 3. Những API Reflection cần biết

| API | Trả về | Vai trò |
| --- | --- | --- |
| `type.getInterfaces()` | `Class<?>[]` | Các interface **trực tiếp** được khai báo trong `implements` của lớp hoặc `extends` của interface; với lớp con, không tự kèm mọi interface của lớp cha. |
| `type.getSuperclass()` | `Class<?>` hoặc `null` | Lớp cha trực tiếp của một lớp; trả `null` với interface, `Object`, primitive và `void`. |
| `type.isInterface()` | `boolean` | Phân biệt nút interface với nút lớp để chỉ đưa interface vào kết quả. |
| `iface.isAssignableFrom(type)` | `boolean` | Kiểm tra `type` có thể gán cho biến kiểu `iface` hay không, bao gồm chính cùng một kiểu. |
| `type.getGenericInterfaces()` | `Type[]` | Đọc dạng generic của interface trực tiếp, ví dụ `Comparable<String>`; đây là bài toán khác với khử trùng lặp theo `Class<?>`. |

**Phân biệt hai hướng truy vấn:**

- `Child.class.getInterfaces()` chỉ cho biết `Diamond` và `Right` khai báo trực tiếp trong `Child`.
- Muốn có `Left` và `Root`, phải đi tiếp qua các interface cha và qua `Base`.
- `Root.class.isAssignableFrom(Child.class)` trả `true` nếu chỉ muốn biết `Child` có thực thi hợp đồng của `Root`, không cần tự dựng danh sách interface.

`Class<?>` đại diện cho danh tính kiểu ở runtime. Hai lớp/interface cùng tên nhị phân nhưng được định nghĩa bởi hai class loader khác nhau có thể là hai đối tượng `Class<?>` khác nhau. Vì vậy hãy lưu **`Class<?>`**, không dùng riêng `getSimpleName()` hoặc `getName()` làm khóa loại trùng.

## 4. Thuật toán BFS tránh lặp

Ta dùng **Breadth-First Search (BFS)** với hàng đợi `ArrayDeque` và tập giữ thứ tự `LinkedHashSet`:

1. Nếu đầu vào là **lớp**, đưa lớp đó vào hàng đợi để khám phá interface trực tiếp và lớp cha. Nếu đầu vào là **interface**, chỉ đưa các *interface cha trực tiếp* vào hàng đợi để loại chính đầu vào khỏi kết quả.
2. Lấy phần tử đầu hàng đợi. Nếu là interface, thử thêm nó vào `visited`. Nếu đã tồn tại, bỏ qua việc mở rộng nút này; nếu mới, thêm các interface cha của nó vào hàng đợi.
3. Nếu là lớp, thêm các interface trực tiếp vào hàng đợi, sau đó thêm lớp cha khi khác `null`. Không thêm nút lớp vào kết quả.
4. Dừng khi hàng đợi rỗng. Chuyển `visited` thành danh sách kết quả.

**Bất biến quan trọng:** một interface chỉ được mở rộng khi lần đầu được đưa vào `visited`. Những đường gặp lại interface đó không tạo thêm phần tử kết quả và không duyệt lại toàn bộ tổ tiên của nó.

`LinkedHashSet` giữ thứ tự **lần đầu gặp** theo BFS. Thứ tự trong ví dụ là thứ tự duyệt có chủ đích; nó không phải một thứ tự phân cấp duy nhất mà mọi công cụ Reflection phải trả về. Nếu sản phẩm cần thứ tự hiển thị cố định theo tên, hãy sắp xếp riêng sau khi thu thập, bằng tên đầy đủ cùng thông tin loader khi cần.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ mã sau vào file **`InterfaceGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class InterfaceGraphDemo {

    interface Root {}
    interface Left extends Root {}
    interface Right extends Root {}
    interface Diamond extends Left, Right {}

    static class Base implements Left {}
    static class Child extends Base implements Diamond, Right {}

    /**
     * Liệt kê mọi interface tổ tiên của type theo BFS,
     * không gồm chính type khi type là interface.
     */
    public static List<Class<?>> allInterfaces(Class<?> type) {
        Objects.requireNonNull(type, "type");

        Set<Class<?>> visited = new LinkedHashSet<>();
        Deque<Class<?>> pending = new ArrayDeque<>();

        if (type.isInterface()) {
            pending.addAll(Arrays.asList(type.getInterfaces()));
        } else {
            pending.addLast(type);
        }

        while (!pending.isEmpty()) {
            Class<?> current = pending.removeFirst();

            if (current.isInterface()) {
                // Đã gặp qua nhánh khác: không thêm và không duyệt lại.
                if (!visited.add(current)) {
                    continue;
                }
                pending.addAll(Arrays.asList(current.getInterfaces()));
            } else {
                // Interface trực tiếp của lớp hiện tại.
                pending.addAll(Arrays.asList(current.getInterfaces()));

                // Lớp con có thể kế thừa interface qua lớp cha.
                Class<?> parent = current.getSuperclass();
                if (parent != null) {
                    pending.addLast(parent);
                }
            }
        }

        return new ArrayList<>(visited);
    }

    private static String names(Collection<Class<?>> types) {
        return types.stream()
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Direct Child: "
                + names(Arrays.asList(Child.class.getInterfaces())));
        System.out.println("All Child: " + names(allInterfaces(Child.class)));
        System.out.println("All Base: " + names(allInterfaces(Base.class)));
        System.out.println("All Diamond: " + names(allInterfaces(Diamond.class)));
        System.out.println("All Root: " + names(allInterfaces(Root.class)));
        System.out.println("All int: " + names(allInterfaces(int.class)));
        System.out.println("Assignable: "
                + Root.class.isAssignableFrom(Child.class));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac InterfaceGraphDemo.java
java InterfaceGraphDemo
```

Kết quả chuẩn của chương trình:

```text
Direct Child: [Diamond, Right]
All Child: [Diamond, Right, Left, Root]
All Base: [Left, Root]
All Diamond: [Left, Right, Root]
All Root: []
All int: []
Assignable: true
```

**Giải thích kết quả:**

- `Direct Child` có đúng hai interface khai báo trong `implements` của `Child`.
- BFS của `Child` gặp `Diamond` rồi `Right`. Sau đó, thuật toán đi vào `Left` (từ `Diamond`) và `Root`. Các lần gặp lại `Right`, `Left`, `Root` qua nhánh khác đều bị bỏ qua.
- `Base` chỉ khai báo `Left` nhưng cũng có `Root` qua `Left extends Root`.
- Với đầu vào `Diamond.class`, ta chủ động bắt đầu từ `Left` và `Right` nên **không đưa `Diamond` vào kết quả**.
- `Root` không có interface cha. `int` không có interface. Cả hai cho danh sách rỗng, nhưng lý do khác nhau.
- `isAssignableFrom` trả `true` vì `Child` gián tiếp thực thi `Root`.

## 6. Vì sao thuật toán không mất và không lặp interface?

**Đủ:** mọi interface tổ tiên đều có một chuỗi cạnh hợp lệ đi từ kiểu đầu vào qua `getInterfaces()` hoặc qua `getSuperclass()` rồi `getInterfaces()`. Thuật toán lần lượt đưa các nút kề vào hàng đợi, nên sẽ đến mỗi interface tổ tiên có thể tới được.

**Không trùng:** chỉ một thao tác `visited.add(current)` trả `true` cho mỗi đối tượng `Class<?>`. Mọi lần gặp tiếp theo đều gặp `false` và bị `continue`, nên kết quả chứa mỗi interface đúng một lần.

**Kết thúc:** số lớp trên chuỗi `getSuperclass()` và số interface tổ tiên của một kiểu Java đã nạp là hữu hạn. Một lớp cha chỉ được đưa vào hàng đợi qua lớp con của nó; mỗi interface chỉ mở rộng một lần. Hàng đợi cuối cùng sẽ rỗng.

Nếu gọi `V` là số nút lớp/interface gặp được và `E` là số cạnh kế thừa/triển khai được xét, thời gian là **O(V + E)**. Bộ nhớ dành cho hàng đợi và tập đã thăm tối đa **O(V + E)** trong cách cài đặt này, bởi một interface có thể được đưa vào hàng đợi từ nhiều cạnh trước khi được xử lý. Chuyển `visited` thành `ArrayList` tốn thêm O(V).

BFS tránh giới hạn độ sâu lời gọi của cách đệ quy thuần. Một bản DFS với `HashSet` hoặc `LinkedHashSet` cũng đúng nếu kiểm tra `visited.add(...)` **trước** khi đi sâu vào các interface cha; điểm khác chủ yếu là thứ tự kết quả và việc dùng call stack.

## 7. Những trường hợp dễ nhầm

### 7.1. Chỉ lấy `getInterfaces()` của lớp con

Sai với mục tiêu “tất cả interface”: `Child.class.getInterfaces()` không tự trả `Left` qua `Base` và cũng không tự khai triển `Root`. Cần duyệt cả hai loại cạnh: **interface → superinterface** và **class → superclass**.

### 7.2. Dùng `List` rồi thêm vô điều kiện

Nếu chỉ cộng dồn interface theo các nhánh, cấu trúc hình thoi sinh phần tử lặp. Hãy dùng `Set<Class<?>>` để kiểm tra danh tính trước khi duyệt tiếp. Không chỉ lọc `distinct()` ở cuối: làm vậy không ngăn các nhánh chung bị xử lý nhiều lần trong lúc duyệt.

### 7.3. Dùng tên interface làm khóa

`getSimpleName()` có thể trùng giữa các package. `getName()` phân biệt package nhưng chưa đủ khi cùng tên được định nghĩa trong các class loader khác nhau. Khóa `Class<?>` bám đúng kiểu runtime; chỉ dùng tên khi **hiển thị**.

### 7.4. Nhầm kiểm tra quan hệ với liệt kê tổ tiên

Nếu chỉ cần hỏi “`Service` có triển khai `Runnable` không?”, dùng:

```java
boolean implementsRunnable = Runnable.class.isAssignableFrom(Service.class);
```

Đây là **đoạn minh họa**, giả sử `Service` là lớp đã được định nghĩa. Khi cần danh sách tất cả interface để xây tài liệu, kiểm tra annotation, phân tích kiểu hoặc tạo báo cáo Reflection, mới cần thuật toán duyệt.

Đặc biệt, `SomeInterface.class.isAssignableFrom(SomeInterface.class)` là `true`, trong khi `allInterfaces(SomeInterface.class)` theo **định nghĩa của bài** không tự chứa `SomeInterface.class`.

### 7.5. Bỏ qua kiểu mảng và kiểu đặc biệt

- `String[].class` có interface trực tiếp `Cloneable` và `java.io.Serializable` theo mô hình kiểu mảng của Java, dù không có mệnh đề `implements` trong mã nguồn.
- Primitive như `int.class` và `void.class` không có interface và không có superclass.
- Interface có `getSuperclass() == null`, nên phải khám phá interface cha bằng `getInterfaces()`.
- `Object.class` không có superclass; vòng lặp phải xử lý `null` an toàn.

### 7.6. Lẫn lộn raw interface và dạng generic

Ví dụ `class X implements Comparable<String>`: `getInterfaces()` trả đối tượng `Class` của `Comparable`, còn `getGenericInterfaces()` có thể biểu diễn `Comparable<String>` dưới dạng `ParameterizedType`. Thuật toán ở đây tìm **danh tính interface**, không suy luận hay hợp nhất các tham số kiểu khi đi qua chuỗi generic. Nếu cần mô hình `Type` chính xác, phải giải bài toán ánh xạ type variable riêng, không chỉ đổi `getInterfaces()` thành `getGenericInterfaces()`.

### 7.7. Tưởng thứ tự là hợp đồng nghiệp vụ

`LinkedHashSet` giữ thứ tự gặp theo BFS, còn độ ưu tiên nhánh chịu ảnh hưởng thứ tự interface trực tiếp do API cung cấp và thứ tự đưa lớp cha vào hàng đợi. Nếu cần danh sách theo tên, sắp xếp rõ ràng; nếu cần độ sâu gần nhất, tính và lưu độ sâu. Đừng dùng chỉ số trong kết quả làm “thứ bậc kế thừa” mặc định.

## 8. Checklist khi dùng trong mã thật

- **Chốt định nghĩa đầu ra:** chỉ tổ tiên, hay có bao gồm chính interface đầu vào? Ví dụ này chọn **không bao gồm**.
- **Đi đủ cạnh:** interface trực tiếp, interface cha của interface và lớp cha của lớp.
- **Thăm một lần:** chỉ mở rộng interface lần đầu `visited.add` trả `true`.
- **Đúng danh tính:** dùng `Class<?>` làm khóa, không dùng chuỗi tên.
- **Xử lý đầu vào:** kiểm tra `null`, kiểu interface, lớp, mảng, primitive; không dựa vào một câu lệnh `implements` trong mã nguồn.
- **Tách mục đích:** cần kiểm tra một quan hệ kiểu thì ưu tiên `isAssignableFrom()`; cần liệt kê toàn bộ quan hệ mới cần duyệt đồ thị.
- **Kiểm chứng cấu trúc hình thoi:** ví dụ `Diamond` phải cho `Root` đúng một lần; trường hợp kế thừa qua `Base` cũng không tạo bản sao.

**Ghi nhớ:** mô hình interface của Java được nhìn từ Reflection như một đồ thị có các nhánh hội tụ. Duyệt mọi cạnh cần thiết, nhưng dùng `visited` theo danh tính `Class<?>` để chỉ xử lý mỗi interface đúng một lần.