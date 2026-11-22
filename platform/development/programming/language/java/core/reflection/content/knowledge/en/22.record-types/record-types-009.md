# Thiết kế công cụ ánh xạ hỗ trợ record và lớp thông thường

## 1. Cùng là dữ liệu đối tượng, nhưng cách tạo khác nhau

Một công cụ ánh xạ thường nhận dữ liệu có tên thuộc tính rồi tạo một đối tượng Java. Ví dụ:

~~~text
{name: " Linh ", age: 20}
    -> đối tượng học viên
~~~

Nếu đối tượng đích là một lớp JavaBean có constructor không tham số và setter, công cụ có thể tạo đối tượng trước rồi gán từng thuộc tính.

Nếu đối tượng đích là record, cách làm phù hợp là chuẩn bị đầy đủ đối số rồi gọi **canonical constructor**. Các thành phần record không có setter để dùng theo mô hình JavaBean thông thường.

Vì vậy, không nên thiết kế một thuật toán duy nhất theo dạng:

~~~text
Tạo đối tượng rỗng
    -> tìm mọi field
    -> mở truy cập
    -> ghi giá trị vào từng field
~~~

Thuật toán đó vừa bỏ qua giao diện của lớp thường, vừa không phù hợp với trường thành phần của record. Trường thành phần record là `private final`; Reflection không cho dùng việc mở truy cập để tùy ý ghi lại các trường final của lớp record. Quy tắc ghi trường được mô tả tại [Field.set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)).

Thiết kế tốt hơn là **dùng chung mô hình thuộc tính và quy tắc kiểm tra**, nhưng có **chiến lược tạo đối tượng phù hợp với từng loại đích**.

## 2. Xác định hợp đồng hỗ trợ trước khi viết Reflection

“Lớp thông thường” bao gồm nhiều thiết kế: JavaBean có setter, lớp bất biến chỉ có constructor, lớp dùng builder, lớp có factory tĩnh hoặc lớp có trường công khai. Không có một thuật toán suy đoán duy nhất phù hợp với mọi loại.

Bài học xây dựng một mapper hai chiều:

~~~text
Map<String, ?> -> đối tượng
đối tượng      -> Map<String, Object>
~~~

Hợp đồng cụ thể của ví dụ:

| Đích | Cách khám phá | Cách tạo | Cách đọc |
| --- | --- | --- | --- |
| Record công khai | `getRecordComponents()` | Canonical constructor công khai | Accessor của từng component |
| JavaBean công khai | `Introspector` và `PropertyDescriptor` | Constructor công khai không tham số, sau đó gọi setter | Getter của từng thuộc tính |

Với nhánh JavaBean, ví dụ yêu cầu các thuộc tính được phát hiện đều đọc và ghi được. Nó từ chối thuộc tính chỉ đọc, chỉ ghi, chỉ truy cập theo chỉ số hoặc accessor tĩnh.

Các giá trị đầu vào đã ở dạng đối tượng Java có kiểu phù hợp. Ví dụ không tự chuyển chuỗi `"20"` thành số, không ánh xạ đệ quy một map lồng nhau thành đối tượng con và không xác minh từng phần tử của một collection generic.

Đó là hợp đồng có chủ đích để thấy rõ kiến trúc. Khi mở rộng, hãy bổ sung chiến lược hoặc bộ chuyển đổi tương ứng, thay vì làm nhánh Reflection âm thầm đoán nhiều cách khác nhau.

## 3. Tách giai đoạn khảo sát và giai đoạn xử lý dữ liệu

Một lần ánh xạ nên có các trách nhiệm rõ ràng:

1. **Khảo sát kiểu đích:** nhận diện record hoặc mô hình JavaBean.
2. **Lập kế hoạch:** lưu tên, kiểu và phương thức truy cập cho từng thuộc tính; xác định constructor.
3. **Kiểm tra dữ liệu đầu vào:** khóa lạ, khóa thiếu, `null`, kiểu giá trị.
4. **Tạo đối tượng:** gọi constructor theo chiến lược đã chọn.
5. **Gán thuộc tính nếu cần:** chỉ ở nhánh JavaBean.
6. **Báo lỗi có ngữ cảnh:** giữ tên thuộc tính hoặc vị trí constructor cùng nguyên nhân.

Metadata không đổi theo từng map dữ liệu. Vì vậy có thể xây một đối tượng mapper cho một `Class<T>`, lập kế hoạch một lần rồi tái sử dụng nó.

Trong ví dụ, mô hình thuộc tính chung là:

~~~java
record Property(String name, Class<?> type, Method reader, Method writer) {
}
~~~

Đây là phần trích từ chương trình sau; cần import `java.lang.reflect.Method` khi dùng độc lập trong một tệp.

- Record có `reader` là accessor và không có `writer`.
- JavaBean có `reader` là getter, `writer` là setter.
- Tên và kiểu được dùng chung cho kiểm tra dữ liệu.
- Cách tạo đối tượng được giữ ở kế hoạch của mapper, không suy ra từ việc `writer` có tồn tại cho từng thuộc tính riêng lẻ.

## 4. Nhánh record: chuẩn bị đối số rồi gọi constructor

Metadata thành phần record cho biết tên, kiểu và thứ tự khai báo. [Class.getRecordComponents](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()) bảo đảm thứ tự các thành phần theo phần đầu record.

Đối với:

~~~java
public record StudentRecord(String name, int age) {
}
~~~

chữ ký canonical constructor dùng thứ tự:

~~~text
(String, int)
~~~

Dù map đầu vào duyệt `age` trước `name`, công cụ vẫn phải tạo mảng đối số theo **thứ tự thành phần record**, không theo thứ tự của map.

Quy trình là:

~~~text
component name -> lấy giá trị theo khóa "name" -> đối số 0
component age  -> lấy giá trị theo khóa "age"  -> đối số 1
    -> gọi canonical constructor
~~~

Những điểm cần tránh:

- Không chọn constructor đầu tiên trong `getDeclaredConstructors()`.
- Không yêu cầu record có constructor không tham số.
- Không suy tên thuộc tính từ `getX()`; accessor record thường tên `x()`.
- Không tạo record rồi cố ghi trực tiếp trường thành phần.
- Không bỏ qua canonical hoặc compact constructor, vì đây có thể là nơi kiểm tra và chuẩn hóa dữ liệu.

Constructor trong ví dụ chuẩn hóa tên bằng `strip()` và từ chối tuổi âm. Mapper phải thực thi logic đó khi tạo record.

## 5. Nhánh JavaBean: dùng mô tả thuộc tính thay vì đoán tên field

`Introspector` khảo sát các thuộc tính JavaBean. Mỗi `PropertyDescriptor` có thể cung cấp kiểu, phương thức đọc và phương thức ghi.

Ví dụ:

~~~text
getName() / setName(String) -> thuộc tính name
getAge()  / setAge(int)     -> thuộc tính age
~~~

Công cụ không cần ghi vào trường `private name` hoặc `private age`. Nó dùng giao diện getter/setter, nhờ đó logic kiểm tra trong setter vẫn được thực thi.

Ví dụ gọi:

~~~java
Introspector.getBeanInfo(type, Object.class)
~~~

để dừng trước `Object`, tránh coi thuộc tính suy ra từ `getClass()` là dữ liệu của mô hình.

Tài liệu [Introspector](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/Introspector.html) và [PropertyDescriptor](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/PropertyDescriptor.html) mô tả các điểm vào này.

Các thuộc tính JavaBean được ví dụ sắp xếp theo tên để có thứ tự ổn định. Thứ tự đó phục vụ kế hoạch và kết quả trình bày; không phải thứ tự khai báo trường của lớp.

Vì sử dụng `java.beans`, chương trình cần module `java.desktop`, có trong JDK đầy đủ. Nếu chuyển sang một dự án dùng `module-info.java`, module của chương trình cần khai báo `requires java.desktop;`.

## 6. Chương trình hoàn chỉnh

Lưu vào `DualModelMapperDemo.java`:

~~~java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class DualModelMapperDemo {
    public record StudentRecord(String name, int age) {
        public StudentRecord {
            name = Objects.requireNonNull(name, "name").strip();
            if (age < 0) {
                throw new IllegalArgumentException("age must be nonnegative");
            }
        }
    }

    public static class StudentBean {
        private String name;
        private int age;

        public StudentBean() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = Objects.requireNonNull(name, "name").strip();
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            if (age < 0) {
                throw new IllegalArgumentException("age must be nonnegative");
            }
            this.age = age;
        }
    }

    record Property(String name, Class<?> type, Method reader, Method writer) {
    }

    public static final class MappingException extends RuntimeException {
        MappingException(String path, Throwable cause) {
            super(path + ": " + cause.getClass().getSimpleName(), cause);
        }
    }

    static MappingException failure(String path, Exception error) {
        Throwable cause = error instanceof InvocationTargetException wrapped
                ? wrapped.getCause() : error;
        return new MappingException(path, cause);
    }

    public static final class Mapper<T> {
        private static final Map<Class<?>, Class<?>> BOXES = Map.of(
                boolean.class, Boolean.class, byte.class, Byte.class,
                short.class, Short.class, char.class, Character.class,
                int.class, Integer.class, long.class, Long.class,
                float.class, Float.class, double.class, Double.class);

        private final Class<T> type;
        private final Constructor<T> constructor;
        private final List<Property> properties;
        private final Set<String> names;
        private final boolean record;

        public Mapper(Class<T> type) {
            this.type = Objects.requireNonNull(type, "type");
            if (!Modifier.isPublic(type.getModifiers())
                    || Modifier.isAbstract(type.getModifiers())
                    || type.isEnum() || type.isInterface()
                    || type.isArray() || type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Unsupported target: " + type.getTypeName());
            }

            record = type.isRecord();
            List<Property> discovered = new ArrayList<>();
            try {
                if (record) {
                    RecordComponent[] components = type.getRecordComponents();
                    Class<?>[] parameterTypes = new Class<?>[components.length];
                    for (int i = 0; i < components.length; i++) {
                        RecordComponent component = components[i];
                        parameterTypes[i] = component.getType();
                        discovered.add(new Property(
                                component.getName(), component.getType(),
                                component.getAccessor(), null));
                    }
                    constructor = type.getConstructor(parameterTypes);
                } else {
                    constructor = type.getConstructor();
                    for (PropertyDescriptor descriptor :
                            Introspector.getBeanInfo(type, Object.class)
                                    .getPropertyDescriptors()) {
                        Method reader = descriptor.getReadMethod();
                        Method writer = descriptor.getWriteMethod();
                        if (descriptor.getPropertyType() == null
                                || reader == null || writer == null
                                || Modifier.isStatic(reader.getModifiers())
                                || Modifier.isStatic(writer.getModifiers())) {
                            throw new IllegalArgumentException(
                                    "Unsupported bean property: "
                                    + descriptor.getName());
                        }
                        discovered.add(new Property(
                                descriptor.getName(),
                                descriptor.getPropertyType(), reader, writer));
                    }
                    discovered.sort(Comparator.comparing(Property::name));
                }
            } catch (ReflectiveOperationException | IntrospectionException ex) {
                throw failure(type.getSimpleName() + ".metadata", ex);
            }
            properties = List.copyOf(discovered);
            names = properties.stream()
                    .map(Property::name)
                    .collect(Collectors.toUnmodifiableSet());
        }

        private Object check(Property property, Object value) {
            Class<?> required = property.type();
            if (value == null) {
                if (required.isPrimitive()) {
                    throw new IllegalArgumentException(
                            "Null primitive: " + property.name());
                }
                return null;
            }
            Class<?> boxed = BOXES.getOrDefault(required, required);
            if (!boxed.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Wrong type for " + property.name()
                        + ": expected " + required.getTypeName());
            }
            return value;
        }

        public T fromMap(Map<String, ?> input) {
            Objects.requireNonNull(input, "input");
            Map<String, ?> source = new LinkedHashMap<>(input);
            for (String name : source.keySet()) {
                if (name == null || !names.contains(name)) {
                    throw new IllegalArgumentException(
                            "Unknown property: " + name);
                }
            }

            Object[] values = new Object[properties.size()];
            for (int i = 0; i < properties.size(); i++) {
                Property property = properties.get(i);
                if (!source.containsKey(property.name())) {
                    throw new IllegalArgumentException(
                            "Missing property: " + property.name());
                }
                values[i] = check(property, source.get(property.name()));
            }

            T result;
            try {
                result = record ? constructor.newInstance(values)
                        : constructor.newInstance();
            } catch (ReflectiveOperationException ex) {
                throw failure(type.getSimpleName() + ".<init>", ex);
            }

            if (!record) {
                for (int i = 0; i < properties.size(); i++) {
                    Property property = properties.get(i);
                    try {
                        property.writer().invoke(result, values[i]);
                    } catch (ReflectiveOperationException ex) {
                        throw failure(type.getSimpleName() + "."
                                + property.name(), ex);
                    }
                }
            }
            return result;
        }

        public Map<String, Object> toMap(T value) {
            Objects.requireNonNull(value, "value");
            type.cast(value);
            Map<String, Object> result = new LinkedHashMap<>();
            for (Property property : properties) {
                try {
                    result.put(property.name(),
                            property.reader().invoke(value));
                } catch (ReflectiveOperationException ex) {
                    throw failure(type.getSimpleName() + "."
                            + property.name(), ex);
                }
            }
            return result;
        }
    }

    static void showFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected a failure: " + label);
        } catch (IllegalArgumentException | MappingException expected) {
            System.out.println(label + ": " + expected.getMessage());
            if (expected.getCause() != null) {
                System.out.println(label + " cause: "
                        + expected.getCause().getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) {
        Mapper<StudentRecord> records = new Mapper<>(StudentRecord.class);
        Mapper<StudentBean> beans = new Mapper<>(StudentBean.class);

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("age", 20);
        input.put("name", " Linh ");

        StudentRecord student = records.fromMap(input);
        StudentBean bean = beans.fromMap(input);
        System.out.println("record: " + student);
        System.out.println("record map: " + records.toMap(student));
        System.out.println("bean map: " + beans.toMap(bean));
        System.out.println("maps equal: "
                + records.toMap(student).equals(beans.toMap(bean)));

        showFailure("missing", () ->
                records.fromMap(Map.of("name", "Linh")));
        showFailure("unknown", () ->
                records.fromMap(Map.of(
                        "name", "Linh", "age", 20, "extra", true)));
        showFailure("wrong type", () ->
                records.fromMap(Map.of("name", "Linh", "age", "20")));

        Map<String, Object> nullAge = new LinkedHashMap<>(input);
        nullAge.put("age", null);
        showFailure("null primitive", () -> records.fromMap(nullAge));

        showFailure("record validation", () ->
                records.fromMap(Map.of("name", "Linh", "age", -1)));
        showFailure("bean validation", () ->
                beans.fromMap(Map.of("name", "Linh", "age", -1)));
    }
}
~~~

Biên dịch và chạy trên classpath thông thường với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 DualModelMapperDemo.java
java DualModelMapperDemo
~~~

Kết quả chính xác:

~~~text
record: StudentRecord[name=Linh, age=20]
record map: {name=Linh, age=20}
bean map: {age=20, name=Linh}
maps equal: true
missing: Missing property: age
unknown: Unknown property: extra
wrong type: Wrong type for age: expected int
null primitive: Null primitive: age
record validation: StudentRecord.<init>: IllegalArgumentException
record validation cause: IllegalArgumentException
bean validation: StudentBean.age: IllegalArgumentException
bean validation cause: IllegalArgumentException
~~~

Trong ví dụ, tất cả các kiểu mô hình và phương thức mà mapper gọi đều công khai, truy cập được trong môi trường chạy. Mapper không tự mở truy cập sâu bằng `setAccessible(true)`.

## 7. Đọc thiết kế qua kết quả thực thi

### 7.1. Hai mô hình dùng chung dữ liệu đầu vào

Map được đưa vào theo thứ tự `age`, rồi `name`. Record vẫn được tạo đúng vì đối số constructor được chuẩn bị theo metadata thành phần, không theo thứ tự map.

Cả compact constructor của record và setter `setName` của JavaBean đều loại khoảng trắng ở hai đầu. Kết quả tên là `Linh`, không còn hai khoảng trắng ban đầu.

Điều này chứng minh mapper đi qua hành vi khởi tạo hoặc hành vi gán mà mô hình đã định nghĩa. Nó không bỏ qua logic đó bằng cách ghi thẳng vào trường.

### 7.2. Map xuất ra có thể khác thứ tự mà vẫn bằng nhau

Kết quả:

~~~text
record map: {name=Linh, age=20}
bean map: {age=20, name=Linh}
maps equal: true
~~~

Nhánh record giữ thứ tự thành phần `name, age`. Nhánh JavaBean sắp xếp thuộc tính theo tên `age, name`.

Hai map có cùng cặp khóa/giá trị nên `Map.equals` cho `true`. Không nên đánh đồng thứ tự trình bày với sự tương đương của dữ liệu map.

Nếu giao thức đầu ra yêu cầu một thứ tự chung cho cả hai mô hình, hãy thiết kế quy tắc đầu ra riêng. Không đổi thứ tự đối số canonical constructor để đạt mục đích trình bày.

### 7.3. Khóa thiếu và null phải được phân biệt

Mapper dùng:

~~~java
source.containsKey(property.name())
~~~

trước khi đọc giá trị.

Vì vậy, hai trường hợp sau không bị nhập làm một:

~~~text
Không có khóa age
Có khóa age nhưng giá trị là null
~~~

Ví dụ chọn chính sách nghiêm ngặt:

- Mọi thuộc tính trong kế hoạch đều phải có khóa.
- `null` bị từ chối nếu kiểu đích là primitive.
- `null` có thể qua bước kiểm tra kiểu của mapper nếu kiểu đích là tham chiếu.
- Constructor hoặc setter vẫn có thể từ chối `null` theo quy tắc của mô hình.

Không tự dùng `0` cho một khóa primitive bị thiếu, cũng không tự bỏ qua khóa thiếu ở JavaBean chỉ vì đối tượng mới có một giá trị mặc định.

### 7.4. Kiểu dữ liệu được kiểm tra trước khi tạo đối tượng

`BOXES` ánh xạ kiểu primitive sang wrapper tương ứng, chẳng hạn `int.class -> Integer.class`. Giá trị `Integer` được chấp nhận cho thuộc tính `int`, còn chuỗi `"20"` bị từ chối.

Chính sách trong ví dụ yêu cầu wrapper tương ứng chính xác cho primitive; nó không tự cho `Byte` đi vào `int` dù một số thao tác Reflection có thể hỗ trợ chuyển đổi mở rộng primitive.

Với kiểu tham chiếu, phép kiểm tra dùng `Class.isInstance(...)`. Giá trị là một lớp con hoặc một triển khai interface phù hợp có thể được chấp nhận.

Đây là kiểm tra theo token kiểu sau xóa kiểu. Nó không chứng minh rằng mọi phần tử của một `List<String>` thực sự là `String`. Muốn xử lý generic, cần giữ và phân tích thêm `Type`, rồi xác định chính sách kiểm tra hoặc chuyển đổi dữ liệu ở từng cấp.

## 8. Giữ nguyên nhân lỗi và vị trí xảy ra

Các lỗi đầu vào như khóa thiếu, khóa lạ và sai kiểu được phát hiện trước bước gọi constructor.

Với lỗi phát sinh trong hành vi của mô hình, Reflection thường bọc ngoại lệ bằng `InvocationTargetException`. Hàm `failure(...)` lấy nguyên nhân gốc và giữ nó làm `cause` của `MappingException`.

Do đó, hai lỗi kiểm tra tuổi âm được định vị khác nhau:

~~~text
StudentRecord.<init>: IllegalArgumentException
StudentBean.age: IllegalArgumentException
~~~

Ở record, lỗi xuất phát từ constructor. Ở JavaBean, lỗi xuất phát từ setter thuộc tính `age`.

Thông tin này hữu ích hơn việc chỉ báo “ánh xạ thất bại”. Khi mở rộng sang dữ liệu lồng nhau, đường dẫn lỗi nên có thêm ngữ cảnh, ví dụ `student.address.city` hoặc `students[2].age`.

Cũng cần tách các nhóm:

| Nhóm lỗi | Ví dụ |
| --- | --- |
| Mô hình đích không thuộc hợp đồng | Enum, lớp trừu tượng, JavaBean có thuộc tính chỉ đọc |
| Không lập được kế hoạch | Thiếu constructor phù hợp hoặc lỗi introspection |
| Dữ liệu đầu vào không phù hợp | Thiếu khóa, khóa lạ, sai kiểu, `null` cho primitive |
| Hành vi mô hình từ chối dữ liệu | Compact constructor hoặc setter ném ngoại lệ |
| Điều kiện truy cập không thỏa | Constructor hoặc phương thức không gọi được từ môi trường hiện tại |

Không nuốt nguyên nhân gốc và trả về một đối tượng mặc định có vẻ hợp lệ. Việc đó làm người dùng công cụ khó biết dữ liệu đã bị bỏ qua hay đối tượng chỉ được khởi tạo một phần.

## 9. Kiểm tra trước không có nghĩa thao tác là giao dịch

Ví dụ kiểm tra tên khóa và kiểu của toàn bộ dữ liệu trước khi tạo đối tượng. Nhờ đó, một chuỗi sai kiểu ở thuộc tính cuối không khiến mapper gọi trước các setter của những thuộc tính đầu.

Tuy nhiên, kiểm tra nghiệp vụ vẫn diễn ra trong constructor hoặc setter:

- Constructor có thể có tác động phụ rồi mới ném ngoại lệ.
- Một setter có thể thành công, setter sau đó thất bại.
- Getter dùng khi xuất map cũng có thể chứa logic hoặc ném ngoại lệ.

Mapper không hoàn tác các tác động phụ đó. Với JavaBean, khi setter thất bại, phương thức không trả về đối tượng đang tạo, nhưng điều này không tạo ra một bảo đảm giao dịch cho toàn bộ mã do lớp mô hình thực thi.

Nếu mô hình cần bảo đảm trạng thái hợp lệ ngay từ đầu, chiến lược tạo qua constructor hoặc factory với đầy đủ dữ liệu thường rõ ràng hơn việc gán tuần tự nhiều setter. Điều đó áp dụng cả cho lớp bất biến thông thường, không chỉ riêng record.

Không sửa quy tắc dữ liệu của mô hình để thuận tiện cho mapper. Hãy chọn cách tạo phù hợp với hợp đồng mô hình.

## 10. Các điểm mở rộng nên đặt thành chính sách riêng

### 10.1. Chuyển đổi kiểu và dữ liệu lồng nhau

Có thể bổ sung một bộ chuyển đổi nhận giá trị nguồn, kiểu đích và đường dẫn hiện tại.

Ví dụ các nhiệm vụ cần quyết định riêng:

- Chuỗi sang số: khoảng trắng, dấu, miền giá trị và tràn số.
- Chuỗi sang enum: tên khai báo hay mã nghiệp vụ, chính sách khi không khớp.
- Map sang đối tượng con: đệ quy theo đúng kiểu đích.
- Danh sách phần tử: phân tích `ParameterizedType`, chuyển đổi từng phần tử và giữ chỉ số trong lỗi.
- `Optional`, ngày giờ hoặc kiểu giá trị riêng: cách biểu diễn nguồn cụ thể.

Không chỉ đưa thêm vài nhánh ép kiểu vào đoạn gọi constructor. Khi dữ liệu phức tạp hơn, chuyển đổi phải hoàn tất và được kiểm tra trước khi chuyển đối số cho chiến lược tạo.

### 10.2. Lớp bất biến thông thường và factory

Một lớp thường có constructor nhiều tham số không nên bị coi là “record chưa được nhận diện”. Nó cần một chiến lược tạo khác, có quy tắc xác định constructor và ánh xạ tên tham số.

Có thể dùng cấu hình tường minh, annotation hoặc một factory được đăng ký. Với constructor thông thường, không mặc định tên tham số Reflection luôn là tên miền dữ liệu nếu chương trình không có metadata hoặc cấu hình phù hợp.

Builder và factory tĩnh cũng nên là chiến lược riêng. Không tự thử hàng loạt constructor theo vị trí mảng rồi chọn lần gọi đầu tiên không ném lỗi.

### 10.3. Annotation và tên ánh xạ

Một công cụ thực tế có thể hỗ trợ tên đầu vào khác tên thuộc tính Java hoặc quy tắc kiểm tra dữ liệu bằng annotation.

Khi đó phải xác định rõ đọc annotation ở đâu:

- Record component.
- Trường lưu trữ.
- Accessor.
- Tham số canonical constructor.
- Vị trí sử dụng kiểu.

Đây là những vị trí metadata khác nhau. Không gộp mọi annotation tìm thấy rồi giả định chúng luôn có cùng ý nghĩa hoặc giá trị. Chính sách ưu tiên và xử lý xung đột cần thuộc hợp đồng mapper.

### 10.4. Đối tượng lồng nhau và chu trình

Khi ánh xạ đệ quy, dữ liệu có thể chứa tham chiếu dùng chung hoặc chu trình. Cần xác định có bảo toàn định danh đối tượng hay chỉ sao chép giá trị.

Record cần đủ đối số trước khi gọi canonical constructor, nên không thể mặc định mọi chu trình đều được xử lý bằng cách tạo đối tượng rỗng rồi ghi bù các trường sau. Nếu không hỗ trợ một cấu trúc chu trình, công cụ nên phát hiện và báo rõ theo đường dẫn dữ liệu.

## 11. Kế hoạch metadata, tái sử dụng và giới hạn hiệu năng

`Mapper<T>` trong chương trình khảo sát kiểu một lần khi được tạo. Mỗi lần `fromMap` hoặc `toMap` sử dụng lại danh sách thuộc tính và constructor đã lưu.

Đó là bước tối ưu có cơ sở: không cần introspection lại cùng một kiểu cho mỗi hàng dữ liệu.

Nếu bổ sung cache dùng chung, khóa phải phản ánh đúng đối tượng `Class<?>`, không chỉ tên lớp. Hai lớp cùng tên từ các class loader khác nhau có thể là những kiểu runtime khác nhau. Vòng đời cache cũng cần phù hợp với vòng đời class loader nếu ứng dụng có nạp hoặc tháo plugin.

Không kết luận mapper Reflection nhanh hoặc chậm chỉ từ một lần chạy chương trình mẫu. Chi phí có thể nằm ở khảo sát metadata, chuyển đổi dữ liệu, kiểm tra nghiệp vụ hoặc chính phương thức accessor. Đo trên công việc thực tế trước khi thay cách gọi bằng một cơ chế khác.

Map xuất ra trong ví dụ là bản sao cấu trúc khóa/giá trị ở mức ngoài. Các đối tượng tham chiếu bên trong vẫn có thể là cùng đối tượng mà getter/accessor trả về. Công cụ không tự sao chép sâu hoặc tạo một ảnh chụp nguyên tử của toàn bộ đồ thị dữ liệu.

## 12. Tự kiểm tra

1. Vì sao không dùng cùng thuật toán “tạo rỗng rồi ghi field” cho JavaBean và record?
2. Vì sao map đầu vào trong ví dụ đưa `age` trước `name` nhưng record vẫn được tạo đúng?
3. Canonical constructor có cần được chọn theo constructor đầu tiên trong mảng Reflection không?
4. Vì sao dùng `containsKey` thay vì chỉ kiểm tra `get(...) == null`?
5. Chuỗi `"20"` có được chương trình tự chuyển thành `int` không?
6. Khi tuổi âm, lỗi của record và JavaBean được báo ở các vị trí nào?
7. Vì sao map xuất ra của record và JavaBean khác thứ tự nhưng vẫn bằng nhau?
8. Việc kiểm tra toàn bộ kiểu dữ liệu trước khi tạo có đảm bảo hoàn tác tác động phụ của setter không?
9. Nếu muốn hỗ trợ một lớp bất biến có constructor ba tham số, nên ép nó qua nhánh JavaBean hay bổ sung chiến lược tạo phù hợp?
10. Việc `List.class.isInstance(value)` trả về `true` có chứng minh mọi phần tử là `String` không?

Đáp án:

1. Record cần được tạo qua constructor phù hợp và có các trường thành phần final; JavaBean trong hợp đồng có cách gán qua setter.
2. Giá trị được lấy theo tên rồi xếp vào mảng theo thứ tự record component, không theo thứ tự map.
3. Không. Cần tìm đúng chữ ký từ danh sách kiểu thành phần theo thứ tự.
4. Để phân biệt thiếu khóa với có khóa mang giá trị `null`.
5. Không. Ví dụ yêu cầu kiểu phù hợp và không thực hiện chuyển đổi chuỗi sang số.
6. `StudentRecord.<init>` và `StudentBean.age`; nguyên nhân nghiệp vụ được giữ làm `cause`.
7. Record dùng thứ tự thành phần, JavaBean dùng thứ tự tên; `Map.equals` so sánh các cặp khóa/giá trị.
8. Không. Đó không phải một giao dịch hoàn tác mã đã được mô hình thực thi.
9. Bổ sung chiến lược tạo có ánh xạ constructor hoặc factory rõ ràng.
10. Không. Phép kiểm tra chỉ xác nhận đối tượng là một danh sách theo kiểu đã xóa; kiểm tra phần tử generic là nhiệm vụ riêng.
