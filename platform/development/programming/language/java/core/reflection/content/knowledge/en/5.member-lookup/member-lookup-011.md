# Xây dựng chính sách tìm kiếm xuyên phân cấp một cách tường minh với Java Reflection

## 1. Vì sao phải có chính sách tra cứu?

Khi viết công cụ dựa trên Java Reflection (mapper, serializer, framework kiểm thử, công cụ kiểm tra metadata), câu hỏi “tìm field/method có tên X” chưa đủ rõ. Ta còn phải quyết định: chỉ xét lớp hiện tại hay cả lớp cha; có đi qua interface không; có lấy thành viên `private`/`protected` không; có giữ các khai báo bị che khuất/ghi đè không; và ưu tiên khai báo nào khi nhiều nơi cùng tên.

Ví dụ, `Child` khai báo field `id` trùng với `Parent.id`. Hai field **cùng tồn tại** và mỗi field có `getDeclaringClass()` khác nhau. Với method `score()` được override, ta thường muốn khai báo gần lớp được hỏi nhất. Nhưng công cụ kiểm toán có thể cần **mọi khai báo**, kể cả khai báo bị che. Vì vậy, kết quả phải đến từ một chính sách có tên, phạm vi và thứ tự ưu tiên được viết rõ trước khi triển khai.

Phân biệt ba yêu cầu thường gặp:

- **Tra cứu thành viên công khai có thể nhìn thấy:** tận dụng `getField` / `getMethod` / `getFields` / `getMethods`, với ngữ nghĩa của API.
- **Kiểm kê khai báo theo từng tầng:** đi qua từng `Class<?>` và dùng `getDeclaredFields` / `getDeclaredMethods`; không gộp các khai báo trùng.
- **Chọn một thành viên theo chính sách ứng dụng:** tự định nghĩa các tầng được thăm, bộ lọc, khóa trùng và quy tắc ưu tiên; ví dụ mã bên dưới thực hiện cách này.

“Được Reflection tìm thấy” **không đồng nghĩa** với “được ngôn ngữ Java kế thừa”, “có quyền truy cập” hay “gọi được”. Đây là bốn vấn đề riêng.

## 2. Các API và ranh giới cần hiểu

| API | Phạm vi và ý nghĩa |
| --- | --- |
| `getDeclaredField(name)` / `getDeclaredFields()` | Field được **khai báo trực tiếp** tại lớp/interface đang xét, bất kể mức truy cập; không tự đi lớp cha. |
| `getField(name)` / `getFields()` | Field `public` của lớp và thành viên `public` được kế thừa/hiển thị từ các lớp cha, interface theo quy tắc Reflection. |
| `getDeclaredMethod(name, parameterTypes...)` / `getDeclaredMethods()` | Method khai báo trực tiếp, kể cả `private`; tìm method theo tên **và kiểu tham số**, không theo kiểu trả về. |
| `getMethod(name, parameterTypes...)` / `getMethods()` | Method `public` được cung cấp trong tập public của kiểu, bao gồm các method kế thừa thích hợp; có thể bao gồm method từ `Object`. |
| `getSuperclass()` | Lấy lớp cha trực tiếp; với `Object` hoặc interface thì trả về `null`. |
| `getInterfaces()` | Lấy các interface trực tiếp được khai báo; muốn thăm cả interface cha, phải tự duyệt tiếp `getInterfaces()`. |
| `getDeclaringClass()` | Xác định chính xác nơi một `Field`/`Method` được khai báo, khác với lớp ban đầu yêu cầu tìm. |

`getDeclared...` là thành phần quan trọng của thuật toán xuyên phân cấp: mỗi lần gọi chỉ xem **một** kiểu, sau đó thuật toán chủ động đi sang kiểu khác. Không nên giả định thứ tự phần tử trả về bởi `getDeclaredFields()` hoặc `getDeclaredMethods()` ổn định; hãy sắp xếp nếu kết quả cần tái lập được.

Constructor không được kế thừa; nếu bài toán yêu cầu constructor, dùng `getDeclaredConstructors()` trên đúng kiểu, không áp dụng thuật toán tìm kiếm constructor dọc lớp cha.

## 3. Hợp đồng chính sách tra cứu

Ví dụ sau định nghĩa ba chế độ:

1. `DECLARED_ONLY`: chỉ kiểu đầu vào.
2. `CLASS_HIERARCHY`: kiểu đầu vào → lớp cha gần nhất → lớp cha tiếp theo; `Object` chỉ xuất hiện khi bật `includeObject`.
3. `WITH_INTERFACES`: trước hết toàn bộ các lớp như trên; sau đó các interface được khai báo từ lớp gần nhất đến lớp xa hơn, đi sâu theo interface cha, bỏ các interface đã thăm.

Hai cờ độc lập:

- `publicOnly`: chỉ nhận thành viên có modifier `public`. Nếu `false`, thu thập cả khai báo không public; **không** tự nâng quyền truy cập.
- `includeObject`: có đưa `Object` vào vòng duyệt lớp cha hay không (mặc định trong ví dụ sử dụng `false`).

Ví dụ chọn thành viên theo quy tắc **first match wins**: với field, khóa trùng là tên; với method, khóa trùng là tên cùng danh sách kiểu tham số. Vì lớp gần được duyệt trước, field bị che và method bị override ưu tiên khai báo gần nhất. Với nhiều interface trùng chữ ký/tên, thứ tự duyệt interface đã định sẽ chọn ứng viên đầu tiên. Nếu nghiệp vụ không cho phép nhập nhằng, thay lựa chọn đầu tiên bằng kiểm tra và báo lỗi rõ ràng. Đây là **chính sách của công cụ**, không tự nhận là thuật toán phân giải tất cả trường hợp gọi method của trình biên dịch Java.

Các kết quả dùng `List.copyOf`/`Optional` để người gọi nhận kết quả dễ kiểm tra và không sửa trực tiếp tập kết quả.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu thành `HierarchyLookupDemo.java`. Chương trình dùng lớp lồng nhau nhằm thể hiện field hiding, covariant return/bridge method, interface mặc định và mức truy cập private.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class HierarchyLookupDemo {
    enum Mode {
        DECLARED_ONLY, CLASS_HIERARCHY, WITH_INTERFACES
    }

    record Policy(Mode mode, boolean publicOnly, boolean includeObject) {
        Policy {
            Objects.requireNonNull(mode);
        }
    }

    record Signature(String name, List<Class<?>> parameters) {}

    interface Named {
        default String label() {
            return "named";
        }
    }

    interface Audited extends Named {
        default void audit() {}
    }

    static class Parent {
        public String id;
        private String secret;

        public Number score() {
            return 1;
        }
    }

    static class Middle extends Parent implements Audited {
        public String id; // Che Parent.id, không xóa Parent.id.
        protected String state;

        @Override
        public Integer score() {
            return 2;
        }
    }

    static final class Leaf extends Middle {
        private String local;

        public void setLocal(String value) {
            local = value;
        }
    }

    // Thứ tự: kiểu đầu vào -> superclass -> ... -> interface trực tiếp,
    // rồi các interface cha (không duyệt trùng trong cấu trúc hình thoi).
    static List<Class<?>> owners(Class<?> start, Policy policy) {
        Objects.requireNonNull(start);
        if (policy.mode() == Mode.DECLARED_ONLY) {
            return List.of(start);
        }

        List<Class<?>> classes = new ArrayList<>();
        for (Class<?> current = start;
             current != null;
             current = current.getSuperclass()) {
            if (current == Object.class && !policy.includeObject()) {
                break;
            }
            classes.add(current);
        }

        if (policy.mode() == Mode.CLASS_HIERARCHY) {
            return List.copyOf(classes);
        }

        Set<Class<?>> ordered = new LinkedHashSet<>(classes);
        for (Class<?> type : classes) {
            for (Class<?> iface : type.getInterfaces()) {
                addInterface(iface, ordered);
            }
        }
        return List.copyOf(ordered);
    }

    static void addInterface(Class<?> iface, Set<Class<?>> ordered) {
        if (ordered.add(iface)) {
            for (Class<?> parent : iface.getInterfaces()) {
                addInterface(parent, ordered);
            }
        }
    }

    static List<Field> fields(Class<?> type, Policy policy) {
        Map<String, Field> chosen = new LinkedHashMap<>();
        for (Class<?> owner : owners(type, policy)) {
            Field[] declared = owner.getDeclaredFields();
            Arrays.sort(declared, Comparator.comparing(Field::getName));
            for (Field field : declared) {
                if (field.isSynthetic()) {
                    continue;
                }
                if (policy.publicOnly()
                        && !Modifier.isPublic(field.getModifiers())) {
                    continue;
                }
                chosen.putIfAbsent(field.getName(), field);
            }
        }
        return List.copyOf(chosen.values());
    }

    static Signature signature(Method method) {
        return new Signature(
                method.getName(),
                List.copyOf(Arrays.asList(method.getParameterTypes())));
    }

    static List<Method> methods(Class<?> type, Policy policy) {
        Map<Signature, Method> chosen = new LinkedHashMap<>();
        for (Class<?> owner : owners(type, policy)) {
            Method[] declared = owner.getDeclaredMethods();
            Arrays.sort(declared,
                    Comparator.comparing(Method::getName)
                            .thenComparing(m -> Arrays.toString(
                                    m.getParameterTypes()))
                            .thenComparing(m -> m.getReturnType().getName()));
            for (Method method : declared) {
                // Compiler có thể sinh bridge cho kiểu trả về hiệp biến.
                if (method.isBridge() || method.isSynthetic()) {
                    continue;
                }
                if (policy.publicOnly()
                        && !Modifier.isPublic(method.getModifiers())) {
                    continue;
                }
                chosen.putIfAbsent(signature(method), method);
            }
        }
        return List.copyOf(chosen.values());
    }

    static Optional<Field> field(
            Class<?> type, String name, Policy policy) {
        return fields(type, policy).stream()
                .filter(f -> f.getName().equals(name))
                .findFirst();
    }

    static Optional<Method> method(
            Class<?> type, String name, Policy policy,
            Class<?>... parameterTypes) {
        Signature expected = new Signature(
                name, List.copyOf(Arrays.asList(parameterTypes)));
        return methods(type, policy).stream()
                .filter(m -> signature(m).equals(expected))
                .findFirst();
    }

    public static void main(String[] args) {
        Policy deep = new Policy(Mode.WITH_INTERFACES, false, false);
        Policy publicOnly = new Policy(Mode.WITH_INTERFACES, true, false);

        System.out.println("field id: "
                + field(Leaf.class, "id", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("method score(): "
                + method(Leaf.class, "score", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("method label(): "
                + method(Leaf.class, "label", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("private local (deep): "
                + field(Leaf.class, "local", deep).isPresent());
        System.out.println("private local (public-only): "
                + field(Leaf.class, "local", publicOnly).isPresent());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 HierarchyLookupDemo.java
java HierarchyLookupDemo
~~~

Kết quả chuẩn:

~~~text
field id: Middle
method score(): Middle
method label(): Named
private local (deep): true
private local (public-only): false
~~~

Lý do kết quả: `Middle.id` được xét trước `Parent.id`; `Middle.score()` được xét trước `Parent.score()`; `label()` khai báo tại `Named`, được tìm thấy khi duyệt `Middle → Audited → Named` trong nhánh interface; `local` là `private` nên chỉ tồn tại trong chế độ cho phép thành viên không public. Method bridge sinh cho `Middle.score()` được lọc để không ảnh hưởng quy tắc chọn chữ ký.

Ví dụ trên **chỉ tìm và trả metadata** `Field`/`Method`. Nó không gọi `setAccessible`, `trySetAccessible`, `Field.get` hay `Method.invoke`.

## 5. Biến thể chính sách theo mục đích thực tế

| Mục tiêu | Quy tắc phù hợp |
| --- | --- |
| Chỉ đọc metadata do kiểu hiện tại định nghĩa | `DECLARED_ONLY`; lưu toàn bộ kết quả nếu cần phân biệt khai báo. |
| Mapping dữ liệu theo field của lớp con và lớp cha | `CLASS_HIERARCHY`; định nghĩa xử lý field cùng tên; thường bỏ static/synthetic/transient theo yêu cầu mapper. |
| Tìm annotation trên method của superclass/interface | `WITH_INTERFACES`; duyệt khai báo theo tầng và dùng `getDeclaredAnnotation` tại từng method; xác định rõ quy tắc kế thừa annotation. |
| Liệt kê API công khai của kiểu | Cân nhắc `getMethods()`/`getFields()` hoặc `publicOnly=true`; so sánh vì policy tùy chỉnh không có nghĩa chính xác như Java member resolution. |
| Công cụ phân tích/kiểm toán | Không dùng `putIfAbsent` để loại khai báo trùng; trả về cặp `(declaringClass, member)` và các vị trí xung đột. |

Một điều chỉnh phổ biến khi viết mapper là lọc `Modifier.isStatic(...)` và `Modifier.isTransient(...)` đối với field. Với scanner method phục vụ nghiệp vụ, có thể bỏ method `static`, method trên `Object`, getter không hợp lệ, hoặc method đã bị override, tùy hợp đồng. Không áp dụng các bộ lọc này một cách ngầm định vì chúng thay đổi kết quả.

**Annotation có quy tắc riêng:** `@Inherited` chỉ liên quan đến việc truy vấn annotation trên *class* theo lớp cha, không khiến annotation trên method hoặc interface tự được kế thừa. Muốn hợp nhất annotation từ method của cha/interface cần định nghĩa thuật toán tìm method tương ứng và chính sách ưu tiên tường minh.

## 6. Những giới hạn và bẫy cần tránh

1. **Tên method chưa phải chữ ký:** overload `load(String)` và `load(int)` là hai method khác nhau. Kiểu tham số trong Reflection phản ánh erasure của generic và kiểu primitive khác kiểu wrapper (`int.class` khác `Integer.class`). Method có kiểu trả về hiệp biến có thể sinh bridge; ví dụ loại bridge/synthetic để phục vụ tra cứu nghiệp vụ. Với công cụ phân tích bytecode, cần giữ chúng.
2. **Field hiding khác method overriding:** Java không có field đa hình theo kiểu method; `Parent.id` vẫn tồn tại khi `Middle` khai báo `id`. Nếu mục đích là kiểm kê, việc gộp bằng tên sẽ mất thông tin. Method `private` hoặc `static` cũng không tuân cùng quy tắc override như method instance có thể override.
3. **Thành viên của interface:** interface có thể có default, static và private method. Việc thuật toán duyệt `getDeclaredMethods()` của interface chỉ nói rằng nó *phát hiện khai báo*, không khẳng định mọi method đó đều được lớp implement kế thừa hay gọi trực tiếp. Nếu cần mô phỏng chính xác khả năng gọi theo ngôn ngữ, phải bổ sung điều kiện về tính thừa kế, static/private, access, override và trường hợp xung đột.
4. **Phạm vi truy cập và module:** tìm thấy thành viên `private` không cấp quyền đọc/gọi. `trySetAccessible()` có thể trả về `false`, còn `setAccessible(true)` có thể ném `InaccessibleObjectException` khi Java Platform Module System không mở package tương ứng; `IllegalAccessException` có thể xảy ra khi thao tác. Chỉ nâng quyền khi có nhu cầu và quyền hợp lệ, không tự mở module để “sửa lỗi tìm kiếm”.
5. **Thứ tự và xung đột:** thứ tự thành viên do Reflection trả về không bảo đảm phù hợp thứ tự nguồn; ví dụ sắp xếp để ổn định. Chế độ first-match cần công bố cách chọn khi nhiều interface cùng tên. Trường hợp cần độ chính xác cao, trả về danh sách ứng viên kèm `declaringClass` rồi báo xung đột thay vì âm thầm chọn.
6. **Hiệu năng và class loader:** Reflection lặp lại trên nhiều đối tượng có chi phí. Cache metadata theo `Class<?>` khi cần (ví dụ `ClassValue`), nhưng phải tránh giữ tham chiếu không cần thiết đến các `ClassLoader` có vòng đời ngắn. Không cache kết quả phụ thuộc chính sách mà quên đưa chính sách vào khóa.
7. **Kiểu đặc biệt:** array, primitive, interface, record và proxy có cấu trúc khai báo khác lớp thông thường. Cần kiểm thử riêng khi ứng dụng hỗ trợ chúng; thuật toán minh họa tập trung vào chuỗi kế thừa class/interface thông thường.

## 7. Tình huống kiểm thử tối thiểu cho chính sách

- `DECLARED_ONLY` tại `Leaf` tìm được `local` nhưng không tìm được `id`.
- `CLASS_HIERARCHY` tại `Leaf` tìm `id` từ `Middle`; không tìm `Named.label()` vì không đi interface.
- `WITH_INTERFACES` tại `Leaf` tìm `Named.label()`; thăm interface cha đúng một lần dù gặp cấu trúc kim cương.
- `publicOnly=true` không trả về `Leaf.local`, `Middle.state` hoặc `Parent.secret`.
- `includeObject=false` không lấy các method khai báo tại `Object` như `toString()` khi chưa override; bật cờ thì có thể tìm thấy.
- Trường hợp overload phân biệt tham số; trường hợp override/bridge ưu tiên khai báo đúng kiểu theo chính sách; trường hợp field cùng tên xác minh `getDeclaringClass()`.
- Khi nghiệp vụ cần giữ mọi khai báo, kiểm thử rằng thuật toán kiểm kê **không** dùng dedup như thuật toán chọn một kết quả.

**Nguyên tắc triển khai:** viết rõ tập kiểu cần duyệt, thứ tự, điều kiện lọc, khóa đồng nhất, cách xử lý xung đột và giới hạn truy cập; sau đó hiện thực các lựa chọn đó thành code có thể kiểm thử. Reflection là công cụ đọc metadata, còn ý nghĩa của việc “tìm xuyên phân cấp” do hợp đồng của ứng dụng quyết định.
