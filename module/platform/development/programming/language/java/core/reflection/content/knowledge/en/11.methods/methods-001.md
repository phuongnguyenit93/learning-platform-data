# Method metadata: tên, lớp khai báo và kiểu trả về trong Java Reflection

Một đối tượng `java.lang.reflect.Method` mô tả **một phương thức** của một lớp hoặc interface. Khi viết công cụ phân tích mã, framework, mapper, bộ sinh tài liệu hay công cụ kiểm thử, ba thông tin thường cần đọc trước tiên là:

- **Tên phương thức**: `method.getName()`.
- **Lớp hoặc interface khai báo phương thức**: `method.getDeclaringClass()`.
- **Kiểu trả về được khai báo**: `method.getReturnType()`.

Ba thuộc tính này là **metadata về phương thức**, không phải kết quả chạy phương thức. Chúng không cần gọi `Method.invoke()` để có giá trị. Tuy nhiên, rất dễ hiểu sai “lớp khai báo” thành “lớp đang được truy vấn” hoặc “lớp của đối tượng nhận”, và hiểu sai “kiểu trả về” thành “kiểu runtime của giá trị được trả về”. Bài học làm rõ các ranh giới đó.

## 1. Method là gì và lấy Method ở đâu?

`Method` thuộc package `java.lang.reflect`, biểu diễn thông tin về phương thức đã được JVM nạp. Thường lấy nó từ một đối tượng `Class<?>`:

```java
Method publicMethod = Example.class.getMethod("run");
Method declaredMethod = Example.class.getDeclaredMethod("run");
```

Đây là đoạn mã minh họa trong ngữ cảnh đã có lớp `Example` với phương thức phù hợp và đã import `Method`; hai lời gọi có thể ném `NoSuchMethodException`.

Hai API tra cứu không đồng nghĩa:

| API của `Class` | Phạm vi tìm |
| --- | --- |
| `getMethod(name, parameterTypes...)` | Phương thức **public** của kiểu, có thể bao gồm phương thức thừa kế từ superclass/superinterface |
| `getDeclaredMethod(name, parameterTypes...)` | Phương thức **được khai báo trực tiếp tại chính kiểu**, bất kể `public`, `protected`, package-private hay `private`; không tìm trong superclass |
| `getMethods()` | Mảng các phương thức public của kiểu và các phương thức được thừa kế theo hợp đồng API |
| `getDeclaredMethods()` | Mảng phương thức được khai báo trực tiếp tại kiểu, không gồm các phương thức thừa kế |

Thứ tự các phần tử của `getMethods()` và `getDeclaredMethods()` **không được bảo đảm là thứ tự khai báo trong source**. Với một phương thức cần xác định chính xác, nên tìm bằng tên và danh sách kiểu tham số; với nhiều phương thức cần trình bày ổn định, tự sắp xếp theo một khóa thích hợp.

Lấy được metadata của một phương thức `private` qua `getDeclaredMethod` **không** tự động cấp quyền gọi phương thức ấy. Việc kiểm tra quyền truy cập khi `invoke` là vấn đề riêng.

## 2. Ba API metadata cốt lõi

### 2.1. getName(): tên đơn giản của phương thức

`String name = method.getName();` trả về **tên phương thức**, ví dụ `"save"`, `"count"`, `"toString"`.

Giá trị chỉ là tên:

- Không chứa tên package hay declaring class.
- Không bao gồm dấu ngoặc tròn, danh sách tham số hoặc kiểu trả về.
- Không đảm bảo phương thức là duy nhất: các overload `parse(String)` và `parse(int)` đều trả `"parse"`.

Muốn định danh overload, kết hợp `getName()` với `getParameterTypes()` (thứ tự tham số là quan trọng). Khi cần thêm metadata cho tài liệu, có thể sử dụng `getModifiers()`, `getGenericParameterTypes()`, `getAnnotations()`... tùy mục đích, nhưng **tên đơn thuần chưa tạo thành chữ ký đầy đủ**.

### 2.2. getDeclaringClass(): kiểu thực sự khai báo phương thức

`Class<?> owner = method.getDeclaringClass();` trả về đối tượng `Class` của **lớp hoặc interface khai báo** phương thức mà `Method` đó biểu diễn.

Ví dụ:

```java
class Parent {
    public void work() {}
}
class Child extends Parent {}
```

Đây là mã minh họa; giả định hai lớp ở ngữ cảnh truy cập hợp lệ.

Nếu tra cứu `Child.class.getMethod("work")`, ta được metadata của phương thức `work` **khai báo trong `Parent`**. Bởi vậy:

```java
Method m = Child.class.getMethod("work");
System.out.println(m.getDeclaringClass() == Parent.class); // true
```

Mặc dù bắt đầu bằng `Child.class`, kết quả vẫn là `Parent.class`, vì `Child` **thừa kế** phương thức chứ không khai báo phương thức mới.

Cần phân biệt ba khái niệm:

| Khái niệm | Cách lấy | Trong ví dụ Child thừa kế Parent.work() |
| --- | --- | --- |
| Kiểu được dùng để bắt đầu truy vấn | Đối tượng `Class` gọi `getMethod` | `Child.class` |
| Kiểu khai báo phương thức được phản chiếu | `Method.getDeclaringClass()` | `Parent.class` |
| Kiểu runtime của receiver khi sử dụng | `receiver.getClass()` | Có thể là `Child.class` hoặc subtype khác |

**Đừng nhầm** `Method.getDeclaringClass()` với `Class.getDeclaringClass()`: cùng tên nhưng gọi trên hai đối tượng khác loại. `Class.getDeclaringClass()` nói về *lớp bên ngoài khai báo một member class*, không phải chủ sở hữu của một phương thức.

Với method được khai báo trong interface, `getDeclaringClass()` có thể trả chính **interface** ấy. Với method được override, một `Method` thuộc lớp con sẽ trả lớp con. Nếu lấy một `Method` trực tiếp từ lớp cha, metadata vẫn có owner là lớp cha ngay cả khi thực thi trên receiver lớp con sử dụng dynamic dispatch.

### 2.3. getReturnType(): kiểu trả về hình thức

`Class<?> returnType = method.getReturnType();` trả về một đối tượng `Class` biểu diễn **kiểu trả về theo khai báo** của phương thức đó.

Ví dụ:

| Khai báo | `getReturnType()` |
| --- | --- |
| `int count()` | `int.class` |
| `String name()` | `String.class` |
| `void reset()` | `void.class` |
| `String[] labels()` | `String[].class` |
| `List<String> tags()` | `List.class` |

**Điểm quan trọng:** `void` được biểu diễn bằng `void.class` (hoặc `Void.TYPE`), **không** phải `null` và cũng không phải `Void.class`. `Void.class` là một lớp wrapper đặc biệt, khác với kiểu `void` của khai báo method.

Khi method khai báo kiểu tham chiếu `Number` nhưng ở runtime trả đối tượng `Integer`, `getReturnType()` vẫn trả `Number.class`: metadata mô tả **khai báo**, không quan sát hoặc chạy method để suy ra kiểu của giá trị. Với phương thức generic như `List<String> tags()`, `getReturnType()` trả `List.class` sau **type erasure**, không lưu được type argument `String` trong chính đối tượng `Class` đó.

## 3. Ví dụ Java 17+ đầy đủ, chạy độc lập

Ví dụ sau cố tình có phương thức thừa kế, override, generic return type, `void`, primitive return type và overload. Nó truy vấn từng method theo tên/chữ ký, nên đầu ra không phụ thuộc thứ tự mảng Reflection.

Tạo tệp `MethodMetadataDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.List;

public class MethodMetadataDemo {
    static class Parent {
        public String inherited() {
            return "parent";
        }

        public String status() {
            return "base";
        }
    }

    static class Child extends Parent {
        @Override
        public String status() {
            return "child";
        }

        public List<String> tags() {
            return List.of("java");
        }

        public int count() {
            return 2;
        }

        public void refresh() {}

        public String parse(String text) {
            return text;
        }

        public String parse(int code) {
            return Integer.toString(code);
        }
    }

    private static void show(Method method) {
        System.out.printf(
                "%s | owner=%s | return=%s%n",
                method.getName(),
                method.getDeclaringClass().getSimpleName(),
                method.getReturnType().getTypeName()
        );
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        show(Child.class.getMethod("inherited"));
        show(Child.class.getMethod("status"));
        show(Child.class.getDeclaredMethod("tags"));
        show(Child.class.getDeclaredMethod("count"));
        show(Child.class.getDeclaredMethod("refresh"));

        Method tags = Child.class.getDeclaredMethod("tags");
        System.out.println(
                "tags generic=" + tags.getGenericReturnType().getTypeName()
        );

        Method overload =
                Child.class.getDeclaredMethod("parse", String.class);
        System.out.println(
                "overload=" + overload.getName()
                + "(" + overload.getParameterTypes()[0].getSimpleName() + ")"
        );

        Method parentStatus = Parent.class.getDeclaredMethod("status");
        System.out.println(
                "parentStatus owner="
                + parentStatus.getDeclaringClass().getSimpleName()
        );
        System.out.println(
                "parentStatus invoked=" + parentStatus.invoke(new Child())
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac MethodMetadataDemo.java
java MethodMetadataDemo
```

Output:

```text
inherited | owner=Parent | return=java.lang.String
status | owner=Child | return=java.lang.String
tags | owner=Child | return=java.util.List
count | owner=Child | return=int
refresh | owner=Child | return=void
tags generic=java.util.List<java.lang.String>
overload=parse(String)
parentStatus owner=Parent
parentStatus invoked=child
```

Giải thích các dòng tiêu biểu:

1. `Child.class.getMethod("inherited")` tìm được phương thức `public inherited()` do **Parent** khai báo. Vì vậy `getDeclaringClass().getSimpleName()` là `Parent`, không phải `Child`.
2. `Child.class.getMethod("status")` tìm phương thức **override do Child khai báo**, nên owner là `Child`.
3. Với `tags()`, `getReturnType().getTypeName()` là `java.util.List`; dùng `getGenericReturnType()` mới thấy thông tin `java.util.List<java.lang.String>`.
4. `count()` trả kiểu nguyên thủy `int`; `refresh()` có kiểu trả về `void`. Cả hai đều có một `Class` hợp lệ biểu diễn kiểu này.
5. `getDeclaredMethod("parse", String.class)` chọn overload có tham số `String`, còn overload `parse(int)` mang cùng tên nhưng chữ ký khác.
6. `parentStatus` là đối tượng `Method` lấy trực tiếp từ `Parent`, nên owner của nó vẫn là `Parent`; tuy nhiên `parentStatus.invoke(new Child())` gọi implementation override của `Child` và trả `"child"`. **Declaring class của metadata** và **implementation được dispatch tại runtime** có thể khác nhau.

Ví dụ được bố trí để mỗi thông tin được in từ một method xác định. Nếu thay các lời gọi này bằng vòng lặp trên `getDeclaredMethods()`, hãy tự sắp xếp trước khi yêu cầu thứ tự output cố định.

## 4. getReturnType() và getGenericReturnType() khác nhau thế nào?

Hai API cùng mô tả **kiểu trả về đã khai báo**, nhưng có mức thông tin khác nhau:

- `getReturnType()` có kiểu Java là `Class<?>`. Nó biểu diễn **kiểu erased/raw** sau khi áp dụng quy tắc erasure cho generic.
- `getGenericReturnType()` có kiểu Java là `java.lang.reflect.Type`. Nó giữ thông tin chữ ký generic khi có, chẳng hạn `ParameterizedType`, `TypeVariable`, `GenericArrayType` hoặc `Class`.

Ví dụ:

```java
public List<String> tags() {
    return List.of("java");
}
```

Trong ngữ cảnh ví dụ chạy ở mục 3, `tags.getReturnType()` là `List.class`, còn `tags.getGenericReturnType().getTypeName()` in ra `java.util.List<java.lang.String>`.

Một ví dụ generic khác:

```java
class Box<T> {
    public T read() {
        return null;
    }
}
```

Đây là đoạn minh họa không độc lập. Với `Method` đại diện cho `Box.read()`, `getReturnType()` là `Object.class` vì `T` không có upper bound cụ thể, còn `getGenericReturnType()` biểu diễn **biến kiểu** `T`.

Nếu `SpecialBox extends Box<String>`, đừng mặc định `SpecialBox.class.getMethod("read").getGenericReturnType()` tự động biến `T` thành `String`: method đó vẫn có thể là metadata khai báo ở `Box`. Để suy ra `T` cụ thể từ subclass, một công cụ phân tích generic phải **resolve mapping type variable** qua hệ thống kiểu của superclass/interface.

Khi xử lý `Type`, nên phân biệt `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`... theo đúng trường hợp thay vì ép mọi `Type` thành `Class`. Dùng `getTypeName()` giúp trình bày thông tin; đừng coi định dạng chuỗi này là giao thức lưu trữ/chữ ký ổn định do ứng dụng tự phát minh.

Nếu chỉ cần phân nhánh theo kiểu runtime đã bị erasure, `getReturnType()` thường đủ. Nếu muốn dựng tài liệu API, phân tích generic hoặc mapper phân biệt `List<String>` với `List<Integer>`, phải xét `getGenericReturnType()` và ngữ cảnh tổng quát hơn.

## 5. Thừa kế, override và dynamic dispatch

Ba khái niệm sau không nên bị nhập làm một:

**Một: kiểu đang truy vấn.** Người viết code có thể bắt đầu bằng `Child.class.getMethod("inherited")`, nhưng truy vấn qua lớp con không có nghĩa mọi `Method` tìm được đều được khai báo ở lớp con.

**Hai: kiểu khai báo.** `method.getDeclaringClass()` là lớp/interface **có khai báo tương ứng** mà Method biểu diễn. Với phương thức inherited không override, thường là lớp cha; với phương thức override được khai báo tại child, là child.

**Ba: implementation được thực thi.** Với instance method sử dụng virtual dispatch, một `Method` trỏ tới khai báo ở lớp cha vẫn có thể chạy implementation override của lớp con khi nhận một object lớp con. Đây là lý do trong ví dụ `parentStatus.getDeclaringClass() == Parent.class` nhưng `parentStatus.invoke(new Child())` trả `"child"`.

Không nên giải thích `getDeclaringClass()` như “lớp định nghĩa implementation thực sự đã chạy”. Trước khi invoke, API chỉ cho biết metadata; dispatch lúc chạy còn tùy loại method (`static`, instance, private...) và receiver.

Với interface, `getDeclaringClass()` có thể trả về interface định nghĩa phương thức. Chẳng hạn method khai báo trong interface `Task` có owner là `Task.class`, dù một lớp cụ thể triển khai `Task`.

## 6. Overload, override, bridge và synthetic methods

**Overload**: nhiều method cùng tên nhưng khác danh sách kiểu tham số. Hai method `parse(String)` và `parse(int)` có cùng kết quả `getName() == "parse"`. Để tìm đúng một method, truyền `Class<?>...` cho `getMethod` hoặc `getDeclaredMethod`:

```java
Method byText = Child.class.getDeclaredMethod("parse", String.class);
Method byCode = Child.class.getDeclaredMethod("parse", int.class);
```

Đoạn trên nằm trong ngữ cảnh lớp `Child` ở ví dụ đầy đủ, với `Method` được import và xử lý `NoSuchMethodException` ở caller. Nếu bỏ tham số khi tìm phương thức `parse`, Java sẽ tìm `parse()` **không tham số**, chứ không tự chọn một overload bất kỳ.

**Override**: một phương thức ở lớp con tái định nghĩa phương thức từ lớp cha. Mỗi khai báo có thể được biểu diễn bằng `Method` riêng, với `getDeclaringClass()` tương ứng. Override có thể dùng **covariant return type** (ví dụ lớp cha khai báo `Number measure()`, lớp con override bằng `Integer measure()`): khi phản chiếu đúng từng khai báo, `getReturnType()` cũng phản ánh kiểu khai báo tương ứng.

**Bridge/synthetic**: compiler đôi khi sinh thêm method ở bytecode để duy trì polymorphism khi dùng generics hoặc covariant returns. Bởi vậy `getDeclaredMethods()` có thể hiển thị nhiều method hơn danh sách người đọc nhìn thấy trong source. Khi phân tích method để sinh tài liệu hoặc đăng ký handler, có thể cần kiểm tra `method.isBridge()` và `method.isSynthetic()`, kết hợp `getParameterTypes()` và `getReturnType()`; không nên coi tên là khóa duy nhất.

Một số class file có thể chứa nhiều method có cùng tên và parameter types nhưng khác return type (ví dụ bridge). Theo hợp đồng `Class.getDeclaredMethod`, khi có nhiều ứng viên và có một kiểu trả về cụ thể hơn những ứng viên còn lại, API ưu tiên ứng viên đó; trường hợp khác có thể chọn một ứng viên. Đừng thiết kế mã phân tích bytecode dựa trên giả định rằng chỉ tên + params luôn phân biệt mọi method ở mức JVM.

**Phương thức khởi tạo không phải Method**: constructor được phản chiếu bằng `Constructor<?>`, không có tên method `"<init>"` lấy từ `getDeclaredMethod`. Việc đọc `Method.getReturnType()` không áp dụng trực tiếp cho `Constructor` vì constructor không có return type kiểu phương thức thông thường.

## 7. Ứng dụng thực tế: xây danh sách metadata có thứ tự

Giả sử cần lập danh sách endpoint, handler hay lệnh từ các method. Tránh hai lỗi: dùng `getName()` làm ID duy nhất trong khi có overload, và dựa vào thứ tự trả về của `getDeclaredMethods()`.

Ví dụ mã minh họa (không phải chương trình độc lập; giả định đã import `Arrays`, `Comparator`, `Method` và có `SomeClass`):

```java
Method[] methods = SomeClass.class.getDeclaredMethods();

Arrays.sort(
        methods,
        Comparator.comparing(Method::getName)
                  .thenComparing(m -> Arrays.toString(m.getParameterTypes()))
                  .thenComparing(m -> m.getReturnType().getTypeName())
);

for (Method method : methods) {
    System.out.printf(
            "%s declaredIn=%s returns=%s%n",
            method.getName(),
            method.getDeclaringClass().getName(),
            method.getReturnType().getTypeName()
    );
}
```

Ví dụ trên tạo thứ tự theo tên, danh sách kiểu tham số (ở dạng chuỗi minh họa) và kiểu trả về; nó **không khôi phục thứ tự khai báo trong source**. Nếu cần khóa định danh lâu dài, định nghĩa một phép mã hóa chữ ký nhất quán, có xét declaring type, method name, ordered parameter types và khi phù hợp cả return type/bridge information. Với mục đích hiển thị đơn giản, comparator ở trên đủ minh họa nguyên tắc.

Khi xây một framework, cũng nên chủ động xác định có muốn bao gồm:

- Method inherited từ superclass/interface hay chỉ method khai báo tại lớp đang xét;
- Method `public` hay cả non-public;
- Method bridge/synthetic do compiler tạo;
- Method được override và các annotation xuất hiện trên từng khai báo.

Các quyết định đó là quy tắc nghiệp vụ của công cụ, **không phải ý nghĩa riêng của `getName`, `getDeclaringClass` hay `getReturnType`**.

## 8. Lỗi phổ biến và cách tránh

| Hiểu lầm | Sự thật |
| --- | --- |
| `Child.class.getMethod("x")` luôn có `getDeclaringClass() == Child.class` | Method có thể khai báo trong parent/interface rồi được thừa kế |
| `getName()` cho biết cả chữ ký method | Chỉ cho biết **tên đơn giản**, không bao gồm tham số |
| `getReturnType()` trả runtime class của giá trị trả về | Trả **kiểu khai báo**, không invoke method |
| `getReturnType()` của `void` là `null` | Là `void.class` |
| `getReturnType()` của `List<String>` giữ `String` | Chỉ có `List.class` sau erasure; dùng `getGenericReturnType()` khi cần generic metadata |
| `getDeclaringClass()` cho biết implementation nào sẽ chạy | Metadata declaration và virtual dispatch là hai vấn đề riêng |
| `getDeclaredMethods()` gồm method inherited | Không; chỉ gồm method khai báo trong chính kiểu |
| Lấy được `private Method` nghĩa là gọi được | Metadata discovery không tự bỏ qua access checks |
| Một method name tương ứng đúng một Method | Overload, compiler bridge/synthetic có thể khiến tên lặp |
| Thứ tự của `getDeclaredMethods()` là thứ tự viết trong file Java | API không bảo đảm thứ tự ấy |

Khi gọi `getMethod` hoặc `getDeclaredMethod` với tên/chữ ký không tìm thấy, `NoSuchMethodException` có thể được ném. Đây là ngoại lệ của **bước tra cứu**, không phải hậu quả của `getName()`, `getDeclaringClass()` hay `getReturnType()` sau khi đã có một đối tượng `Method` hợp lệ.

Các lời gọi `Method.invoke` còn có thể bị kiểm tra quyền truy cập, ném `IllegalAccessException`, `InvocationTargetException` và các lỗi khác. Metadata không tự cho phép thực thi hay bảo đảm method chạy thành công.

## 9. Checklist và câu hỏi tự kiểm tra

Trước khi dùng Method metadata trong chương trình, có thể kiểm tra theo thứ tự:

1. Mình cần *method khai báo trực tiếp* hay cả *method kế thừa*? Chọn `getDeclaredMethod(s)` hoặc `getMethod(s)` tương ứng.
2. Mình có cần phân biệt overload? Dùng tên cùng kiểu tham số theo thứ tự, đừng chỉ dùng `getName()`.
3. Mình đang hỏi *declaring class* hay *kiểu runtime của receiver*? Chọn đúng nguồn metadata.
4. Mình cần *return type erased* hay *generic return signature*? Dùng `getReturnType()` hoặc `getGenericReturnType()`.
5. Mình có cần chạy method không? Nếu không, dừng ở metadata; nếu có, xử lý quyền truy cập, receiver và ngoại lệ riêng.
6. Mình có đang dựa vào thứ tự liệt kê hoặc bỏ sót bridge/synthetic methods không? Chọn bộ lọc/sắp xếp tường minh.

### Câu hỏi

1. `Method.getName()` của `parse(String)` là gì? **`"parse"`**; không chứa `String`.
2. Gọi `Child.class.getMethod("inherited")` đối với phương thức chỉ khai báo trong Parent, `getDeclaringClass()` là gì? **`Parent.class`**.
3. `void refresh()` có `getReturnType()` bằng `null` không? **Không.** Kết quả là `void.class`.
4. `List<String> tags()` có `getReturnType()` bằng `List<String>.class` không? **Không có class literal ấy**; kết quả là `List.class`, generic information nằm ở `getGenericReturnType()`.
5. Một `Method` đại diện cho `Parent.status()` được invoke với receiver `Child` đã override, owner của Method có đổi không? **Không.** Owner vẫn `Parent`, dù virtual dispatch có thể chạy `Child.status()`.
6. Muốn tìm `parse(int)` mà không bị nhầm `parse(String)`, dùng gì? **`getDeclaredMethod("parse", int.class)`** trong đúng lớp khai báo.
7. Lấy metadata method bằng `getDeclaredMethod` có tự cho quyền gọi method `private` không? **Không.** Quyền truy cập khi thực thi được kiểm tra riêng.

## 10. Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): định nghĩa `getName()`, `getDeclaringClass()`, `getReturnType()`, `getGenericReturnType()`, bridge/synthetic và invocation.
- [Oracle Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): phân biệt `getMethod`, `getDeclaredMethod`, `getMethods`, `getDeclaredMethods` và quy tắc tra cứu.
- [Java Language Specification SE 21 — §8.4 Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4): nền tảng overload, override và return types.

**Ghi nhớ:** `getName()` trả *tên*, `getDeclaringClass()` trả *kiểu khai báo phương thức*, `getReturnType()` trả *kiểu trả về hình thức sau erasure*. Khi cần metadata generic, dùng thêm `getGenericReturnType()`; khi cần biết implementation sẽ chạy, phải xét dynamic dispatch và receiver chứ không suy từ declaring class.