# Annotation trên interface hoặc phương thức không tự truyền như annotation lớp

Trong Java Reflection, annotation đặt trên **lớp**, **interface** và **phương thức** không tuân theo cùng một quy tắc kế thừa. Meta-annotation `@Inherited` chỉ khiến annotation trên **class cha** có thể được tìm khi truy vấn **class con** theo chuỗi superclass. Nó **không** tự truyền annotation từ interface sang implementing class, từ superinterface sang subinterface, hay từ method cha/interface sang method override/implementation.

Vì vậy, khi xử lý **annotation runtime**, cần phân biệt ba việc: annotation **được khai báo trực tiếp** tại đâu, method Reflection đang biểu diễn **method nào**, và ứng dụng có yêu cầu thêm quy tắc tìm kiếm ngoài Java Reflection chuẩn hay không. Sự khác biệt quyết định kết quả của `getAnnotation`, `getDeclaredAnnotation` và các API liên quan.

## 1. Retention, Target và Inherited là ba khái niệm khác nhau

Định nghĩa một annotation có thể đặt trên type/method và đọc ở runtime:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Label {
    String value();
}
```

Đoạn trên là **định nghĩa minh họa**, lưu trong `Label.java` nếu công bố annotation top-level `public`. Ví dụ hoàn chỉnh ở mục 4 khai báo `Label` bên trong class để chỉ dùng một file.

| Meta-annotation | Tác dụng | Không có nghĩa là |
| --- | --- | --- |
| `@Retention(RUNTIME)` | Giữ annotation để các API Reflection có thể đọc lúc chạy | Annotation sẽ được kế thừa |
| `@Target(TYPE)` / `@Target(METHOD)` | Cho phép áp dụng annotation ở vị trí type hoặc method | Annotation trên interface/method sẽ tự truyền |
| `@Inherited` | Khi truy vấn annotation của một **class**, nếu class chưa khai báo nó, Reflection có thể tìm ở **superclass** | Interface, method, field, parameter tự kế thừa annotation |

`@Inherited` chỉ là meta-annotation gắn với **định nghĩa annotation type**. Dù `Label` được phép dùng trên method (`@Target(METHOD)`), hiệu ứng `@Inherited` **vẫn không áp dụng cho method**.

Một annotation muốn được quan sát bằng `Class.getAnnotation` hoặc `Method.getAnnotation` phải có runtime retention. Retention mặc định nếu bỏ `@Retention` là `CLASS`, không phù hợp với ví dụ đọc annotation lúc chạy.

## 2. Mốc so sánh: annotation trên superclass

Giả sử `Label` có `@Inherited`, `@Retention(RUNTIME)` và `@Target(TYPE)`, `Base` mang `@Label("base-class")` còn `Child extends Base` không khai báo nhãn. Khi hỏi `Child.class.getAnnotation(Label.class)`, Reflection nhận nhãn từ `Base`; `Child.class.getDeclaredAnnotation(Label.class)` trả `null`. Nếu `Child` tự mang `@Label("child-class")`, nhãn riêng thắng.

Đây là **quy tắc tra annotation tại class declaration**, không sao chép annotation vào bytecode của `Child`. Phần tiếp theo đối chiếu quy tắc này với interface và method, là hai trường hợp Java Reflection xử lý khác.

## 3. Interface và method không tự kế thừa annotation

### 3.1. Interface được annotatе trực tiếp, class triển khai không tự có

```java
@Label("contract")
interface Contract {}

class Implementation implements Contract {}
```

`Contract.class.getAnnotation(Label.class)` trả annotation trực tiếp trên `Contract`. `Implementation.class.getAnnotation(Label.class)` trả `null` nếu `Implementation` không có annotation tương ứng từ superclass. Tương tự, `interface Sub extends Contract` cũng không tự có annotation của `Contract` theo `@Inherited`.

Nếu một framework muốn coi annotation của interface có hiệu lực trên implementing class, framework cần **chủ động tìm trong interfaces**, rồi áp dụng chính sách riêng về thứ tự và xung đột.

### 3.2. Method override không tự có annotation của parent method

```java
class Parent {
    @Label("parent-operation")
    public void execute() {}
}
class Child extends Parent {
    @Override
    public void execute() {}
}
```

`Child.class.getDeclaredMethod("execute").getAnnotation(Label.class)` trả `null` vì method `Child.execute` được khai báo mới và không tự có `@Label` của `Parent.execute`. Dù `Label` mang `@Inherited`, Reflection không tự duyệt overridden method.

Method interface cũng tương tự: annotation trên `Contract.execute()` không tự xuất hiện ở `Implementation.execute()`.

### 3.3. Kế thừa method mà **không override** là trường hợp khác

```java
class Parent {
    @Label("parent-method")
    public void work() {}
}
class Child extends Parent {}
```

`Child.class.getMethod("work")` có thể trả `Method` khai báo tại `Parent`; `getDeclaringClass()` cho thấy `Parent.class`. Nếu đọc `getAnnotation(Label.class)` trên chính `Method` đó, ta vẫn thấy `@Label("parent-method")` vì **đang đọc metadata method của Parent**, không phải annotation đã được sao chép lên một method khác tại Child.

Các ví dụ ở mục 3 là tình huống minh họa riêng biệt; không đặt nhiều class `Parent` trùng tên trong cùng một file. Mục tiếp theo có chương trình chạy hoàn chỉnh, phân biệt các trường hợp bằng tên rõ ràng.

## 4. Ví dụ Java 17+ có thể biên dịch/chạy

Tạo tệp `AnnotationInheritanceDemo.java` với nội dung:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class AnnotationInheritanceDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Label {
        String value();
    }

    @Label("base-class")
    static class Base {
        @Label("base-inherited-method")
        public void inheritedMethod() {}

        @Label("base-override-method")
        public void overriddenMethod() {}
    }

    static class Child extends Base {
        @Override
        public void overriddenMethod() {}
    }

    @Label("interface-type")
    interface Contract {
        @Label("interface-method")
        void execute();
    }

    static class Implementation implements Contract {
        @Override
        public void execute() {}
    }

    public static void main(String[] args) throws Exception {
        System.out.println("child.class=" +
                Child.class.getAnnotation(Label.class).value());
        System.out.println("child.declaredAbsent=" +
                (Child.class.getDeclaredAnnotation(Label.class) == null));

        System.out.println("interface.direct=" +
                Contract.class.getAnnotation(Label.class).value());
        System.out.println("implementation.interfaceAbsent=" +
                (Implementation.class.getAnnotation(Label.class) == null));

        Method inherited =
                Child.class.getMethod("inheritedMethod");
        System.out.println("inheritedMethod.owner=" +
                inherited.getDeclaringClass().getSimpleName());
        System.out.println("inheritedMethod.label=" +
                inherited.getAnnotation(Label.class).value());

        Method overridden =
                Child.class.getMethod("overriddenMethod");
        System.out.println("overriddenMethod.owner=" +
                overridden.getDeclaringClass().getSimpleName());
        System.out.println("overriddenMethod.labelAbsent=" +
                (overridden.getAnnotation(Label.class) == null));
        System.out.println("parentMethod.label=" +
                Base.class.getMethod("overriddenMethod")
                        .getAnnotation(Label.class).value());

        Method implemented =
                Implementation.class.getMethod("execute");
        System.out.println("implementedMethod.labelAbsent=" +
                (implemented.getAnnotation(Label.class) == null));
        System.out.println("interfaceMethod.label=" +
                Contract.class.getMethod("execute")
                        .getAnnotation(Label.class).value());
    }
}
```

Chạy ở thư mục chứa tệp, với Java 17 trở lên:

```bash
javac AnnotationInheritanceDemo.java
java AnnotationInheritanceDemo
```

Kết quả stdout:

```text
child.class=base-class
child.declaredAbsent=true
interface.direct=interface-type
implementation.interfaceAbsent=true
inheritedMethod.owner=Base
inheritedMethod.label=base-inherited-method
overriddenMethod.owner=Child
overriddenMethod.labelAbsent=true
parentMethod.label=base-override-method
implementedMethod.labelAbsent=true
interfaceMethod.label=interface-method
```

**Giải thích từng nhóm kết quả:**

1. `Child` kế thừa **kết quả tra cứu annotation ở cấp class** từ `Base` do `Label` mang `@Inherited`. `getDeclaredAnnotation` vẫn trả `null` vì `Child` không tự khai báo.
2. `Contract` được gắn `@Label` trực tiếp nên đọc được `interface-type`; `Implementation` triển khai `Contract` nhưng không tự nhận annotation đó.
3. `inheritedMethod` không bị `Child` override; `Child.class.getMethod(...)` trả đối tượng `Method` của `Base` nên `getDeclaringClass()` là `Base` và `Label` vẫn có trên method ấy.
4. `overriddenMethod` là method khai báo ở `Child`; annotation `Label` không được truyền từ method `Base`. Truy vấn trực tiếp `Base.overriddenMethod` vẫn có `base-override-method`.
5. `Implementation.execute` không tự có annotation của `Contract.execute`. Muốn đọc `interface-method` phải truy vấn method khai báo trên interface.

Trong ví dụ chỉ **đọc metadata**, không cần gọi `setAccessible(true)` hoặc thực thi các method đích. Kết quả không phụ thuộc vào thứ tự trả về của các mảng Reflection.

## 5. Chọn API theo phần tử đang truy vấn

| API | Khi nào dùng? |
| --- | --- |
| `getAnnotation(A.class)` / `isAnnotationPresent(A.class)` | Hỏi annotation *present* trên phần tử; chỉ khi phần tử là class mới có thể xét `@Inherited`. |
| `getDeclaredAnnotation(A.class)` | Chỉ hỏi annotation được khai báo trực tiếp, không tìm superclass. |
| `getAnnotations()` / `getDeclaredAnnotations()` | Liệt kê annotation theo phạm vi tương ứng, không tự mở container repeatable. |
| `getAnnotationsByType(A.class)` / `getDeclaredAnnotationsByType(A.class)` | Đọc cả các `@Repeatable` gián tiếp trong container, có hoặc không xét inheritance phù hợp. |

Trên một `Method` đại diện cho khai báo override, cả hai getter một-annotation đều đọc **method hiện tại**; nếu cần annotation trên method cha/interface, phải chủ động duyệt quan hệ method. Không suy ra một method đã nhận annotation kế thừa chỉ vì `getMethod()` trả một khai báo từ superclass.

## 6. Khi muốn lấy annotation method cha, phải tự duyệt

Một thư viện đôi khi muốn method override dùng annotation khai báo trên method cha. Đây là **quy tắc tự thiết kế**; Java Reflection mặc định không làm vậy.

Ví dụ helper tìm annotation trực tiếp trên các method trùng tên/chữ ký trong superclass chain:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;

static <A extends Annotation> A findFromClassHierarchy(
        Class<?> start,
        String methodName,
        Class<?>[] parameterTypes,
        Class<A> annotationType) {
    for (Class<?> current = start;
         current != null;
         current = current.getSuperclass()) {
        try {
            Method method = current.getDeclaredMethod(
                    methodName, parameterTypes);
            A annotation = method.getDeclaredAnnotation(annotationType);
            if (annotation != null) {
                return annotation;
            }
        } catch (NoSuchMethodException ignored) {
            // Lớp này không khai báo method với chữ ký đã tìm.
        }
    }
    return null;
}
```

Đây là **helper minh họa** cần đặt bên trong một class và không có `main`. Nó có thể tìm `@Label("base-override-method")` ở `Base.overriddenMethod` khi bắt đầu từ `Child` và không thấy `Label` tại method `Child`.

**Giới hạn quan trọng:** đoạn này tìm theo **tên và kiểu tham số giống nhau**, chưa chứng minh hai method có quan hệ override hợp lệ theo Java. Nó không loại trường hợp `private`, `static`, synthetic/bridge method, không xét visibility, và không duyệt các interface. Nếu framework cần ngữ nghĩa kế thừa annotation chặt chẽ, phải xử lý riêng các điều kiện này, đặc biệt với generics, covariant return và nhiều superclass/interface.

## 7. Muốn tìm annotation của interface, cũng cần chính sách riêng

Trong chương trình ở mục 4:

```java
Label interfaceLabel =
        Contract.class.getAnnotation(Label.class);
Method interfaceMethod =
        Contract.class.getMethod("execute");
Label methodLabel =
        interfaceMethod.getAnnotation(Label.class);
```

Đoạn này là **mã minh họa**, cần khai báo `Contract`/`Label`, import `Method` và xử lý `NoSuchMethodException`. Nó đọc trực tiếp annotation ở interface và method do interface khai báo; không làm `Implementation` mang annotation ấy.

Nếu class động triển khai nhiều interface, có thể truy cập `Class.getInterfaces()` để tự duyệt; cần xem xét superinterface và các interface do superclass triển khai khi bài toán cần, cũng như tránh thăm lặp. Nếu hai interface có cùng annotation nhưng khác giá trị, ứng dụng phải xác định quy tắc ưu tiên/xung đột. **Không có một chính sách Java Reflection mặc định** rằng annotation interface nào sẽ được “truyền” cho implementation.

Các framework có thể triển khai cơ chế merged-annotation, tìm annotation trên interface hoặc method hierarchy theo chính sách riêng. Đó là hành vi của framework, không thay đổi hợp đồng `@Inherited` hay `Class.getAnnotation` trong Java chuẩn. Khi phụ thuộc framework, cần kiểm tra đúng phiên bản và API cụ thể.

## 8. Các lỗi hiểu sai thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| `@Inherited` giúp annotation interface truyền sang implementing class | Chỉ xét superclass khi truy vấn class; interface không tự truyền |
| `@Inherited` giúp method override nhận annotation từ method cha | Không áp dụng cho method |
| `@Target(TYPE, METHOD)` làm annotation có cơ chế kế thừa ở cả hai nơi | Target chỉ giới hạn vị trí đặt annotation |
| `@Retention(RUNTIME)` có nghĩa là annotation được kế thừa | Runtime retention chỉ giúp Reflection nhìn thấy |
| `Child.getMethod("work").getAnnotation(...)` thấy annotation nên method con đã được annotate | Nếu không override, đối tượng `Method` có thể là method của superclass |
| `getAnnotation` và `getDeclaredAnnotation` là tương đương | `getDeclaredAnnotation` chỉ đọc khai báo trực tiếp; `getAnnotation` trên class có thể xét `@Inherited` |
| Annotation trên `Contract.execute` tự xuất hiện ở `Implementation.execute` | Phải truy vấn interface method hoặc có cơ chế tìm riêng |
| Method có `@Override` sẽ được copy annotation từ parent | `@Override` là kiểm tra tại biên dịch, không tự sao chép runtime annotation |
| API framework tìm thấy interface annotation tức là Reflection chuẩn cũng vậy | Framework có thể duyệt hierarchy theo quy tắc bổ sung |

## 9. Checklist xử lý annotation runtime

1. **Xác định phần tử chứa annotation:** class, interface, method hay phần tử khác? Cơ chế `@Inherited` chỉ áp dụng với class qua superclass.
2. **Kiểm tra retention:** cần `RetentionPolicy.RUNTIME` cho việc đọc annotation qua Reflection lúc chạy.
3. **Kiểm tra target:** `ElementType.TYPE` cho class/interface, `METHOD` cho method; target không quy định inheritance.
4. **Chọn đúng API:** `getDeclaredAnnotation` để đọc trực tiếp; `getAnnotation` khi cần semantics “present” của element.
5. **Nếu đọc method kế thừa, xem `getDeclaringClass()`:** có thể đang lấy metadata của method cha chứ không phải annotation được truyền.
6. **Nếu đọc method override/implement, đừng trông chờ @Inherited:** tự kiểm tra parent method/interface method khi chính sách ứng dụng cần.
7. **Nếu có nhiều nguồn annotation, xác định ưu tiên rõ ràng:** superclass, interfaces, overridden methods, repeatable container và xung đột phải có contract.
8. **Kiểm chứng bằng test cho framework:** kết quả từ cơ chế tìm kiếm mở rộng không thể suy ra chỉ từ API Reflection chuẩn.

## 10. Tài liệu gốc

- [`@Inherited` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): phạm vi inheritance giới hạn ở annotation trên class và superclass.
- [`AnnotatedElement` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): ý nghĩa của annotation present, declared, associated và các API truy vấn.

**Ghi nhớ:** `@Inherited` chỉ có hiệu lực khi **truy vấn annotation trên một class qua superclass chain**. Interface và method có annotation của riêng chúng; lớp triển khai interface hoặc phương thức override không tự nhận annotation đó. Khi cần hành vi truyền từ interface/method, phải xây quy tắc tìm kiếm riêng và kiểm tra rõ declaring class, quan hệ override, độ ưu tiên và runtime retention.