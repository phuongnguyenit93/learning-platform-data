# Duyệt toàn bộ chuỗi lớp cha trong Java Reflection

## 1. Mục tiêu và mô hình kế thừa

Khi biết một lớp, ta có thể dùng Reflection để lần lượt tìm **lớp cha trực tiếp**, **lớp ông**, rồi tiếp tục đến `java.lang.Object`. Với khai báo `Leaf extends Middle` và `Middle extends Base`, còn `Base` không viết `extends`, chuỗi đầy đủ từ lớp con là:

```text
Leaf -> Middle -> Base -> Object -> null
```

`null` chỉ là dấu hiệu đã hết chuỗi, **không phải một lớp**. Java cho một class kế thừa trực tiếp tối đa một class, vì vậy đường đi qua các **superclass** là tuyến tính. Đây là cơ sở để kiểm tra metadata kế thừa, tìm field hoặc method do lớp cha khai báo, xây dựng serializer/mapper và chẩn đoán cấu trúc runtime.

Phân biệt ngay từ đầu: quan hệ class `extends` khác với quan hệ interface `implements`/`extends`. Một class có thể triển khai nhiều interface. Các interface **không xuất hiện** trong chuỗi lấy bằng `getSuperclass()`.

## 2. API `Class.getSuperclass()` hoạt động thế nào?

Một lớp hoặc kiểu Java có đối tượng metadata `Class<?>` ở runtime. Gọi:

```java
Class<?> parent = current.getSuperclass();
```

sẽ nhận đối tượng `Class` của **superclass trực tiếp** của `current`. Khi không có superclass theo hợp đồng Reflection, phương thức trả `null`.

| Biểu thức | Kết quả |
| --- | --- |
| `Leaf.class.getSuperclass()` | `Middle.class` |
| `Middle.class.getSuperclass()` | `Base.class` |
| `Base.class.getSuperclass()` | `Object.class`, nếu `Base` không khai báo `extends` |
| `Object.class.getSuperclass()` | `null` |
| `Runnable.class.getSuperclass()` | `null`, do đây là interface |
| `int.class.getSuperclass()` và `void.class.getSuperclass()` | `null` |
| `String[].class.getSuperclass()` | `Object.class` |

`Class<?>` được dùng khi ta cần duyệt metadata mà không biết tham số kiểu cụ thể. Không cần khởi tạo object của từng lớp, và việc gọi `getSuperclass()` không chạy constructor của chúng.

Đừng viết liên tiếp `type.getSuperclass().getSuperclass()` mà thiếu kiểm tra, bởi khi tới `Object`, kết quả kế tiếp là `null`; gọi tiếp trên `null` gây `NullPointerException`. Vòng lặp phải luôn kiểm tra điều kiện dừng.

## 3. Thuật toán: đi từ lớp hiện tại đến `Object`

Các bước:

1. Chọn `Class<?>` bắt đầu, chẳng hạn `Leaf.class` hoặc `someObject.getClass()`.
2. Nếu muốn kể cả lớp đó, xử lý/lưu nó ngay; nếu chỉ muốn các lớp cha, bắt đầu ở `start.getSuperclass()`.
3. Lấy superclass của lớp hiện tại bằng `getSuperclass()`, chuyển sang lớp đó.
4. Lặp cho đến khi `current == null`.

Thời gian O(h), trong đó h là độ dài chuỗi lớp. Bộ nhớ phụ O(1) khi chỉ in/xử lý từng lớp; nếu trả về một danh sách h lớp thì dùng O(h) bộ nhớ.

### Chương trình Java 17+ hoàn chỉnh

Lưu chương trình dưới tên **`SuperclassChainDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class SuperclassChainDemo {
    static class Base {}
    static class Middle extends Base {}
    static class Leaf extends Middle {}

    // includeStart = true: có lớp đầu vào; false: chỉ các lớp cha.
    public static List<Class<?>> classChain(Class<?> start, boolean includeStart) {
        if (start == null) {
            throw new IllegalArgumentException("start không được null");
        }

        List<Class<?>> result = new ArrayList<>();
        for (Class<?> current = includeStart ? start : start.getSuperclass();
             current != null;
             current = current.getSuperclass()) {
            result.add(current);
        }
        return List.copyOf(result);
    }

    private static String names(List<Class<?>> classes) {
        return classes.stream()
                .map(Class::getSimpleName)
                .collect(Collectors.joining(" -> "));
    }

    public static void main(String[] args) {
        System.out.println("Gồm lớp bắt đầu: " + names(classChain(Leaf.class, true)));
        System.out.println("Chỉ các lớp cha: " + names(classChain(Leaf.class, false)));
        System.out.println("Từ Object: " + names(classChain(Object.class, true)));
    }
}
```

Chạy tại thư mục chứa file:

```bash
javac SuperclassChainDemo.java
java SuperclassChainDemo
```

Kết quả stdout:

```text
Gồm lớp bắt đầu: Leaf -> Middle -> Base -> Object
Chỉ các lớp cha: Middle -> Base -> Object
Từ Object: Object
```

Giải thích: vòng lặp bắt đầu tại `Leaf.class`, sau đó chuyển qua `Middle.class`, `Base.class`, `Object.class`; lần gọi `Object.class.getSuperclass()` nhận `null` nên dừng. Khi `includeStart=false`, lớp đầu tiên đưa vào danh sách là `Middle`. `List.copyOf` làm cho danh sách kết quả không thể bị thay đổi qua các thao tác thêm/xóa phần tử; đây là lựa chọn thiết kế, không phải điều kiện bắt buộc để duyệt.

Nếu chỉ cần thực thi một thao tác trên mỗi lớp, không phải tích lũy `List`, vòng `while` sau là đủ. Đây là **đoạn code minh họa** sử dụng `Leaf` trong ví dụ trên, không phải chương trình độc lập:

```java
Class<?> current = Leaf.class;
while (current != null) {
    System.out.println(current.getSimpleName());
    current = current.getSuperclass();
}
```

Chọn `getSimpleName()` để hiển thị tên ngắn; `getName()` trả tên nhị phân của lớp, thích hợp hơn khi cần biết package hoặc phân biệt nested class (nested class có thể chứa dấu `$` trong tên nhị phân). Tên ngắn có thể trùng nhau, vì vậy đừng dùng riêng `getSimpleName()` làm khóa định danh duy nhất.

## 4. Chọn điểm bắt đầu và điểm dừng

| Nhu cầu | Cách thực hiện |
| --- | --- |
| Gồm chính lớp được truyền vào | `current = start` |
| Chỉ duyệt các lớp cha | `current = start.getSuperclass()` |
| Gồm cả `Object` | Lặp khi `current != null` |
| Bỏ `Object` khỏi kết quả | Lặp khi `current != null && current != Object.class` |
| Theo lớp khai báo rõ trong code | Dùng `MyType.class` |
| Theo kiểu thực tế của một object | Dùng `instance.getClass()` sau khi chắc chắn `instance != null` |

Ví dụ một biến có kiểu khai báo `Base` nhưng thực tế chứa `new Leaf()`: `instance.getClass()` trả `Leaf.class`, nên thuật toán đi từ `Leaf`. Đây là điều quan trọng khi làm việc với subclass do framework hoặc thư viện sinh ở runtime. Với `Object.class` và lựa chọn **chỉ lớp cha**, kết quả hợp lệ là danh sách rỗng.

## 5. Ứng dụng thực tế: quét metadata qua từng superclass

Các API Reflection có phạm vi rất khác nhau. `getDeclaredFields()` chỉ trả những field **khai báo trực tiếp trong lớp đang xét**, bất kể phạm vi truy cập; nó không tự gom field được khai báo ở tổ tiên. Vì vậy, nếu công cụ cần tìm field trên toàn chuỗi lớp, hãy duyệt từ lớp con lên từng lớp cha rồi gọi `getDeclaredFields()` ở **mỗi** cấp.

Ví dụ minh họa đặt trong ngữ cảnh có biến `Class<?> type`:

```java
for (Class<?> current = type;
     current != null;
     current = current.getSuperclass()) {
    System.out.println("Khai báo tại " + current.getName());

    for (java.lang.reflect.Field field : current.getDeclaredFields()) {
        System.out.println("  field: " + field.getName());
    }
}
```

Đoạn này liệt kê metadata kể cả field `private` trong superclass. **Đọc được metadata không có nghĩa có quyền truy cập giá trị** của field. Việc gọi `Field.get(...)` hoặc yêu cầu bỏ qua kiểm tra truy cập còn phụ thuộc quy tắc Java và hệ thống module JPMS. Không mặc định mọi field đều được `setAccessible(true)` thành công.

Bảng so sánh quan trọng:

| API | Ý nghĩa phạm vi |
| --- | --- |
| `getDeclaredFields()` | Field khai báo tại **chính lớp đó**, không tự gom superclass |
| `getFields()` | Field `public` theo hợp đồng API, bao gồm field public kế thừa |
| `getDeclaredMethods()` | Method khai báo tại **chính lớp đó**, không tự gom superclass |
| `getMethods()` | Method `public` theo hợp đồng API, gồm các method công khai được kế thừa |

Cần quyết định rõ chính sách đối với metadata trùng tên. Một subclass có thể khai báo field cùng tên với field của superclass (**field hiding**). Khi quét từng cấp, cả hai field có thể được thấy; nếu xây mapper, cần chọn ưu tiên khai báo gần lớp con nhất hay giữ tất cả. Với method, còn phải xét override, overload, method synthetic/bridge, quyền truy cập và interface. Vòng lặp superclass chỉ cung cấp đường duyệt đúng; cách hợp nhất thành viên là một bài toán riêng.

## 6. Những trường hợp đặc biệt

### 6.1. Interface là một nhánh quan hệ khác

Với `class Worker extends Base implements Runnable`, duyệt `Worker.class.getSuperclass()` sẽ đi qua `Base` và `Object`, không qua `Runnable`. Gọi `getInterfaces()` để lấy interface trực tiếp của class; với một interface, API này trả những superinterface trực tiếp của nó.

Nếu nhiệm vụ là tìm **tất cả** interface trên các cấp lớp, cần duyệt interface ở từng superclass, đi tiếp qua những superinterface, đồng thời đánh dấu interface đã thăm để không lặp kết quả khi nhiều nhánh hội tụ. Đó là duyệt một đồ thị quan hệ kiểu, khác với chuỗi superclass của bài này.

Khi chỉ cần hỏi một kiểu có gán được sang kiểu khác hay không, hãy cân nhắc `Target.class.isAssignableFrom(Source.class)`; đây là phép kiểm tra quan hệ kiểu do Java cung cấp, thường không cần viết thuật toán duyệt thủ công.

### 6.2. `Object`, primitive, `void` và array

- `Object.class.getSuperclass()` là `null` và là điểm dừng tự nhiên của các chuỗi class thông thường.
- Kiểu nguyên thủy như `int.class`, kiểu `void.class` và kiểu interface đều có `getSuperclass() == null`. Đừng tự thêm `Object` vào kết quả của chúng.
- Với class của mảng như `String[].class` hoặc `int[].class`, `getSuperclass()` trả `Object.class`. Mảng cũng triển khai `Cloneable` và `java.io.Serializable`, nhưng các interface này không xuất hiện trong chuỗi superclass.
- Các kiểu enum kế thừa lớp `java.lang.Enum`; record kế thừa `java.lang.Record`. Vòng lặp chung vẫn đi đúng lên `Object`, không cần mã riêng.

### 6.3. Generic superclass và type erasure

Với khai báo `class StringBox extends Box<String>`, `getSuperclass()` trả metadata lớp cha thô tương ứng `Box.class`. Nó không cung cấp trực tiếp toàn bộ biểu thức kiểu `Box<String>`. Khi cần phân tích thông tin generic trong khai báo `extends`, dùng `getGenericSuperclass()` (kiểu trả về là `java.lang.reflect.Type`, có thể là `ParameterizedType`) và kiểm tra loại `Type` trước khi ép kiểu. Đừng nhầm metadata generic được lưu trong chữ ký khai báo với khả năng phục hồi tùy ý tham số generic của mọi object ở runtime.

### 6.4. Danh tính lớp và class loader

`Class<?>` biểu diễn đúng kiểu đã được nạp. Hai class cùng tên nhưng được nạp bởi hai class loader khác nhau có thể có danh tính kiểu khác nhau. Khi xử lý kết quả Reflection cho plugin/proxy/framework, nên giữ đối tượng `Class<?>` (hoặc bổ sung thông tin loader khi cần), thay vì dựa riêng vào chuỗi tên ngắn. Việc duyệt chỉ đọc cấu trúc lớp ở runtime; nó không khẳng định đối tượng có thể được khởi tạo hay một thành viên private có thể truy cập.

## 7. Lỗi thường gặp

| Lỗi | Vì sao sai và cách sửa |
| --- | --- |
| Gọi tiếp `getSuperclass()` trên `null` | Gây `NullPointerException`; kiểm tra `current != null` trước mỗi lượt |
| Dừng ngay trước `Object` khi yêu cầu toàn bộ chuỗi | Mất lớp gốc; chỉ loại `Object` khi bài toán yêu cầu |
| Mong `getSuperclass()` trả cả interface | API này chỉ xét superclass; dùng `getInterfaces()` cho interface |
| Chỉ đọc `Leaf.class.getDeclaredFields()` | Không thấy field khai báo ở superclass; quét mỗi cấp riêng |
| Nghĩ `getSuperclass()` cho biết `Box<String>` | API trả `Class`; xét `getGenericSuperclass()` nếu cần chữ ký generic |
| Dùng `getSimpleName()` làm khóa duy nhất | Có thể trùng giữa package hoặc nested class; giữ `Class<?>` hoặc định danh đầy đủ thích hợp |
| Coi `Class` được tìm ra là có thể truy cập mọi thành viên | Quy tắc Java/JPMS vẫn được áp dụng khi truy cập thành viên |

## 8. Câu hỏi tự kiểm tra

1. Cho `C extends B`, `B extends A`, `A` không ghi `extends`. `classChain(C.class, true)` có những phần tử nào và thứ tự ra sao?
2. Vì sao `classChain(C.class, false)` không có `C` nhưng vẫn có `Object`?
3. Với `class C implements Runnable`, làm thế nào để lấy `Runnable`? Có thể dùng `getSuperclass()` không?
4. Cần tìm các field `private` được **khai báo** trong cả các superclass: nên dùng `getFields()` trên lớp con hay `getDeclaredFields()` cho từng cấp? Vì sao?
5. `Object.class.getSuperclass()` và `String[].class.getSuperclass()` trả kết quả giống nhau hay khác nhau?

**Đáp án:** (1) `C, B, A, Object`; (2) khởi tạo từ superclass của `C` nhưng vẫn duyệt đến trước `null`; (3) dùng `getInterfaces()` cho interface trực tiếp, không dùng `getSuperclass()`; (4) dùng `getDeclaredFields()` tại từng lớp, vì API đó nhìn thấy khai báo của lớp tương ứng; (5) `Object` trả `null`, mảng trả `Object.class`.

Cốt lõi của bài là giữ biến `Class<?> current`, liên tục cập nhật bằng `current.getSuperclass()` cho tới `null`. Cách làm này thu được đầy đủ và đúng thứ tự **chuỗi lớp cha**; muốn bao gồm interface, generic hoặc kết hợp metadata thành viên phải áp dụng thêm API và quy tắc riêng cho từng mục đích.