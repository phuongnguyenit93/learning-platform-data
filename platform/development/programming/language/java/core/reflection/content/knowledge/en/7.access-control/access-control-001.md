# Tra cứu thấy thành viên không đồng nghĩa được quyền sử dụng

## 1. Ý tưởng cốt lõi: tìm thấy metadata khác với được truy cập

Trong Java Reflection, một chương trình có thể **tìm thấy mô tả của thành viên** (`Field`, `Method`, `Constructor`) mà vẫn **không có quyền đọc trường, ghi trường, gọi phương thức hoặc tạo đối tượng qua constructor**. Đây là điểm dễ nhầm khi bắt đầu dùng `getDeclaredField()`, `getDeclaredMethod()` và `getDeclaredConstructor()`.

Ví dụ tưởng tượng:

```java
Field secret = Account.class.getDeclaredField("passwordHash");
```

Nếu lớp `Account` có trường `private` tên `passwordHash`, lệnh trên vẫn có thể trả một đối tượng `Field`. Điều đó chỉ chứng minh rằng trường được **khai báo** và được Reflection **phát hiện**. Lệnh tiếp theo như `secret.get(account)` vẫn có thể ném `IllegalAccessException` vì mã gọi không có quyền truy cập.

Nên phân biệt ít nhất ba bước:

1. **Tra cứu thành viên:** Xác định lớp, tên, chữ ký và nhận metadata.
2. **Kiểm tra quyền:** Quyết định mã gọi có thể sử dụng thành viên đó hay có được phép yêu cầu bỏ qua kiểm tra quyền Java thông thường hay không.
3. **Thao tác thực sự:** `Field.get/set`, `Method.invoke` hoặc `Constructor.newInstance`, với đối tượng đích và đối số hợp lệ.

```text
Class<?> và tên/chữ ký thành viên
              |
              v
     getDeclaredXxx / getXxx
              |
      Có tìm thấy không?
         /           \
      Không           Có
       |               |
NoSuch...Exception     v
              Đã có Field/Method/Constructor
                         |
                         v
              Kiểm tra quyền truy cập
                   /            \
             Không đủ          Đủ quyền
                 |                |
        Không thể sử dụng     get/set/invoke/
        trực tiếp             newInstance
```

**Khả năng tra cứu và khả năng truy cập là hai câu hỏi độc lập.** Có metadata không làm biến mất `private`, giới hạn package, quan hệ kế thừa hoặc quy tắc Java Platform Module System (JPMS).

## 2. Tìm thành viên bằng `getXxx` và `getDeclaredXxx`

`Class<?>` cung cấp hai họ API quan trọng:

| Thành viên | Tra cứu dạng public | Tra cứu do chính kiểu khai báo |
|---|---|---|
| Trường | `getField(name)`, `getFields()` | `getDeclaredField(name)`, `getDeclaredFields()` |
| Phương thức | `getMethod(name, parameterTypes...)`, `getMethods()` | `getDeclaredMethod(name, parameterTypes...)`, `getDeclaredMethods()` |
| Constructor | `getConstructor(parameterTypes...)`, `getConstructors()` | `getDeclaredConstructor(parameterTypes...)`, `getDeclaredConstructors()` |

Cách hiểu:

- `getField` và `getMethod` tìm các thành viên **public** theo quy tắc của API, có thể bao gồm thành viên thừa kế.
- `getDeclaredField` và `getDeclaredMethod` xem các thành viên **khai báo trong chính lớp/interface đang xét**, kể cả `private`, `protected` và package-private. Các API declared không tự cộng thêm thành viên kế thừa.
- Constructor không được kế thừa; sự khác biệt giữa `getConstructor` và `getDeclaredConstructor` chủ yếu là phạm vi `public` hay mọi mức truy cập.
- `getDeclaredXxx` không có nghĩa “cho phép dùng private member”. Từ *declared* mô tả **phạm vi tìm kiếm**, không phải quyền.
- `getXxx` tìm được một thành viên `public` cũng chưa bảo đảm thao tác phản chiếu thành công: lớp khai báo có thể không truy cập được từ mã gọi, package có thể không được module xuất, hoặc đối tượng đích/đối số không hợp lệ.

Ví dụ minh họa (giả sử `Profile` có trường `private String token`):

```java
Field f = Profile.class.getDeclaredField("token");
System.out.println(f.getName()); // token

// Dòng dưới đây KHÔNG được bảo đảm thành công:
Object value = f.get(profile);
```

Đoạn này chỉ minh họa ý nghĩa API; `Profile` và `profile` là thành phần giả định, chưa phải chương trình độc lập. Chương trình đầy đủ có thể chạy được trình bày ở mục 3.

Lỗi `NoSuchFieldException` hoặc `NoSuchMethodException` có nghĩa **không tìm thấy thành viên theo tên/chữ ký/phạm vi tra cứu đã chọn**. Nó khác `IllegalAccessException`, khi metadata đã tồn tại nhưng thao tác bị từ chối. Ví dụ `getDeclaredMethod("pay", int.class)` không tìm `pay(Integer)`, dù Java có cơ chế boxing trong lời gọi mã nguồn thông thường.

## 3. Ví dụ chạy được trên Java 17+: chứng minh “tìm thấy ≠ được dùng”

Chương trình dưới đây định nghĩa **hai lớp top-level riêng biệt trong cùng một file**. `Vault` chứa private field và private method; `AccessLookupDemo` là caller khác lớp và khác nest, vì vậy **không có quyền truy cập private theo ngôn ngữ Java**. Tuy nhiên cả hai nằm cùng unnamed module, nên `trySetAccessible` có thể bật suppression và minh họa sự khác nhau.

Lưu nguyên văn vào file **`AccessLookupDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class AccessLookupDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Vault vault = new Vault("abc123");

        Field field = Vault.class.getDeclaredField("secret");
        System.out.println("field found: " + field.getName());
        System.out.println("field public: "
                + Modifier.isPublic(field.getModifiers()));
        System.out.println("field canAccess before: "
                + field.canAccess(vault));

        try {
            field.get(vault);
            System.out.println("field read unexpectedly succeeded");
        } catch (IllegalAccessException ex) {
            System.out.println("field get: "
                    + ex.getClass().getSimpleName());
        }

        boolean fieldOpened = field.trySetAccessible();
        System.out.println("field trySetAccessible: " + fieldOpened);
        System.out.println("field canAccess after: "
                + field.canAccess(vault));

        if (fieldOpened) {
            System.out.println("field value: " + field.get(vault));
        }

        Method method = Vault.class.getDeclaredMethod("formatSecret");
        System.out.println("method found: " + method.getName());
        System.out.println("method canAccess before: "
                + method.canAccess(vault));

        try {
            method.invoke(vault);
            System.out.println("method invoke unexpectedly succeeded");
        } catch (IllegalAccessException ex) {
            System.out.println("method invoke: "
                    + ex.getClass().getSimpleName());
        }

        boolean methodOpened = method.trySetAccessible();
        System.out.println("method trySetAccessible: " + methodOpened);

        if (methodOpened) {
            System.out.println("method result: "
                    + method.invoke(vault));
        }
    }
}

class Vault {
    private final String secret;

    Vault(String secret) {
        this.secret = secret;
    }

    private String formatSecret() {
        return "[" + secret + "]";
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac AccessLookupDemo.java
java AccessLookupDemo
```

Kết quả kỳ vọng khi chạy thông thường, không có agent/cấu hình thay đổi quyền Reflection:

```text
field found: secret
field public: false
field canAccess before: false
field get: IllegalAccessException
field trySetAccessible: true
field canAccess after: true
field value: abc123
method found: formatSecret
method canAccess before: false
method invoke: IllegalAccessException
method trySetAccessible: true
method result: [abc123]
```

Giải thích từng mốc:

1. `getDeclaredField("secret")` và `getDeclaredMethod("formatSecret")` **tìm thấy** private member. Không có ngoại lệ lookup.
2. `Modifier.isPublic(...)` trả `false`; `canAccess(vault)` ban đầu cũng trả `false` vì caller không có quyền private.
3. `field.get(vault)` và `method.invoke(vault)` ban đầu ném `IllegalAccessException` **trước khi truy cập nội dung/thi hành phương thức**. Việc bắt ngoại lệ giúp chương trình tiếp tục.
4. `trySetAccessible()` trả `true` trong ví dụ này vì hai top-level classes cùng unnamed module và không bị một ràng buộc access khác từ môi trường ngăn cản.
5. Sau khi bật suppression trên từng metadata object, `field.get(vault)` và `method.invoke(vault)` thành công.
6. `Vault` là lớp top-level thứ hai không có modifier `public`. Java cho phép khai báo nhiều lớp top-level trong cùng một `.java` nhưng chỉ một lớp `public` phù hợp tên file.

Ví dụ cho thấy rõ **không phải metadata khiến private member sử dụng được**, mà là caller sau đó đã được runtime cho phép bật suppression trên đối tượng Reflection cụ thể.

## 4. Chẩn đoán một lỗi truy cập theo đúng giai đoạn

| Giai đoạn | Triệu chứng | Cần kiểm tra |
| --- | --- | --- |
| Tra cứu | `NoSuchFieldException`, `NoSuchMethodException` | Đúng tên, chữ ký, lớp khai báo, phạm vi `getXxx` hay `getDeclaredXxx` chưa? |
| Kiểm tra quyền | `canAccess(receiver) == false` | Caller có quyền theo Java không? Lớp khai báo và package/module có truy cập được không? |
| Mở quyền | `trySetAccessible() == false` hoặc `InaccessibleObjectException` | Named module có `opens` package cho caller không? Có thực sự cần deep reflection không? |
| Thực thi | `IllegalAccessException` | Metadata đã tìm được, nhưng caller chưa có quyền sử dụng member |
| Chạy mã đích | `InvocationTargetException` | Method/constructor đã chạy và ném exception; đọc `getCause()` |
| Kiểm tra đối số | `IllegalArgumentException` | Receiver, kiểu/số đối số hoặc giá trị gán có hợp lệ không? |

Một member `public` vẫn có thể bị chặn nếu *lớp khai báo* không truy cập được. Một member `private` có thể được gọi bình thường từ chính lớp hoặc nestmate hợp lệ; kết quả kiểm tra phụ thuộc caller. `trySetAccessible()` chỉ thử bỏ qua kiểm tra truy cập và vẫn chịu ranh giới JPMS; thành công không bảo đảm có thể ghi mọi trường `final`.

## 5. Tự kiểm tra

1. Vì sao `getDeclaredField("secret")` tìm được member dù `Field.get` có thể ném `IllegalAccessException`?
2. Vì sao `getMethod` tìm được một method `public` vẫn chưa bảo đảm `Method.invoke` được phép?
3. Hai lớp top-level ở cùng tệp nguồn có trở thành nestmate không? Vì sao ví dụ dùng hai lớp riêng?
4. Vì sao `exports` và `opens` ảnh hưởng khác nhau đến public API và deep reflection?
5. Khi `Method.invoke` trả `InvocationTargetException`, bạn cần điều tra quyền Reflection hay lỗi từ code đã chạy?

**Bài học cần giữ:** lookup xác định metadata **tồn tại**; quyền sử dụng được quyết định riêng tại điểm thao tác. Chọn đúng họ `getXxx`/`getDeclaredXxx` trước, rồi mới đánh giá caller, receiver và module.