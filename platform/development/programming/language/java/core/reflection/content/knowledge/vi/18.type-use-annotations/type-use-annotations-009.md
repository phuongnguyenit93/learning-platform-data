# Xây dựng trình duyệt cây kiểu mà vẫn giữ vị trí annotation

Trong Java Reflection, một kiểu như **List<String>** không chỉ có tên kiểu và type arguments: từng **vị trí sử dụng kiểu** (type-use) có thể mang annotation riêng. Đặc biệt trong cấu trúc nested generics, wildcards, arrays, owner types và type-variable bounds, **vị trí** annotation quan trọng không kém **giá trị** annotation. Một trình duyệt chỉ gom các annotation thành một danh sách phẳng sẽ làm mất ngữ nghĩa.

Bài học thuộc chủ đề **Annotation trên kiểu** và hướng dẫn cách xây dựng một *visitor* đi qua cây **AnnotatedType**, lưu đường dẫn cho từng nút và không làm nhầm annotation ở kiểu gốc với annotation trên kiểu con. Mục tiêu là dùng được trong trình hiển thị metadata, serializer, validator, bộ phân tích generic hoặc công cụ sinh schema.

## 1. Annotation trên declaration và annotation trên type-use

Hai loại vị trí phải được phân biệt:

- **Declaration annotation** gắn với khai báo class, field, method, constructor, parameter hoặc type parameter. Ví dụ annotation target FIELD được đọc từ Field.getDeclaredAnnotations().
- **Type-use annotation** gắn với một vị trí sử dụng kiểu, ví dụ List có annotation riêng, String bên trong List có annotation riêng, hoặc một chiều của mảng có annotation riêng. Metadata này được truy cập qua AnnotatedType và các biến thể.

Ví dụ Java minh họa:

~~~java
import java.lang.annotation.*;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Column {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Tag {
    String value();
}

class Example {
    @Column
    @Tag("list") List<@Tag("element") String> names;
}
~~~

Ở đây **@Column** gắn vào khai báo field; **@Tag("list")** thuộc nút kiểu gốc List<String>; **@Tag("element")** thuộc type argument String. Nếu kiểm tra duy nhất Field.getDeclaredAnnotations(), ta không thu được cây annotation gắn trên tất cả các vị trí generic.

**Điều kiện quan trọng:** core Reflection ở runtime chỉ thấy những annotation có RetentionPolicy.RUNTIME. Annotation với SOURCE hoặc CLASS retention có thể tồn tại ở source/class file nhưng không hiện diện qua các lời gọi Reflection runtime tương ứng. Khi cần phân tích class file sâu hơn, phải dùng công cụ bytecode khác.

## 2. Vì sao chỉ duyệt Type không đủ?

**Type** cùng các dạng **ParameterizedType**, **TypeVariable**, **WildcardType**, **GenericArrayType** cung cấp cấu trúc của kiểu. Tuy nhiên, tự duyệt Field.getGenericType() rồi tách các thành phần Type không giúp bảo toàn đầy đủ annotations gắn ở từng type-use.

Thay vì:

~~~java
Type onlyStructure = field.getGenericType();
~~~

hãy lấy root có annotation:

~~~java
AnnotatedType annotatedRoot = field.getAnnotatedType();
~~~

**AnnotatedType.getType()** vẫn trả cấu trúc Type của nút hiện tại, nhưng **AnnotatedType.getAnnotationsByType(...)** và **getDeclaredAnnotations()** đọc annotation tại **chính nút** đó. Muốn xuống type arguments, array dimensions, bounds hoặc owner, phải dùng API chuyên biệt trên các subtype.

Chẳng hạn:

~~~text
@Tag("list") List<@Tag("element") String>
                 |
field            |      annotation = list
└── field.arg[0] |      annotation = element
~~~

Không được báo rằng cả hai annotation cùng nằm trên List hoặc cùng nằm trên String. Việc phân biệt hai nút là mục đích chính của visitor.

## 3. Các dạng nút phải hỗ trợ

| Kiểu node Reflection | Cấu trúc mẫu | Lời gọi lấy con | Quy ước đường dẫn |
|---|---|---|---|
| AnnotatedParameterizedType | List<String>, Map<K,V> | getAnnotatedActualTypeArguments() | .arg[0], .arg[1] |
| AnnotatedArrayType | String[] hoặc String[][] | getAnnotatedGenericComponentType() | .component |
| AnnotatedWildcardType | ? extends Number; ? super Integer | getAnnotatedUpperBounds(), getAnnotatedLowerBounds() | .upper[0], .lower[0] |
| AnnotatedTypeVariable | T trong List<T> | getAnnotatedBounds() | .bound[0] |
| AnnotatedType có owner | Outer.Inner<String> | getAnnotatedOwnerType() | .owner |
| Nút leaf | String, Number, int | Không duyệt con | Giữ node và annotation tại node |

Ở mọi nhánh, visitor thực hiện theo thứ tự: **đọc và xuất annotation tại node hiện tại**, sau đó **đi vào các node con**. Một annotation trên node cha không tự động kế thừa xuống node con.

Với **Map<@A String, @B List<@C Integer>>**, các đường dẫn tương ứng là:

~~~text
field.arg[0]                 -> @A trên String
field.arg[1]                 -> @B trên List<Integer>
field.arg[1].arg[0]          -> @C trên Integer
~~~

Đường dẫn được dựng từ các cạnh thật trong mô hình Reflection, không phải bằng cách tìm chuỗi con trong Type.getTypeName().

## 4. Thiết kế node và đường dẫn

Trong một công cụ thực tế, bản ghi cho mỗi node tối thiểu gồm:

| Thuộc tính | Ví dụ | Tác dụng |
|---|---|---|
| path | field.arg[0].upper[0] | Giữ chính xác vị trí |
| kind | WILDCARD, PARAMETERIZED, ARRAY... | Mô tả dạng node |
| typeName | java.lang.Number | Kiểu tại node |
| annotations | Tag("upper") | Chỉ annotation tại node |
| declarationSource | Field, return, parameter... | Tránh nhầm root khác nhau |

Java 17 cho phép dùng record để biểu diễn:

~~~java
record TypeNode(
    String path,
    String kind,
    String typeName,
    java.util.List<String> annotations
) {}
~~~

Đây là một khai báo record minh họa; visitor trong phần tiếp theo in trực tiếp để giảm mã phụ trợ. Khi cần xuất JSON, vẽ cây hay lưu database, hãy thay lệnh in bằng việc tạo các TypeNode tương ứng.

**Không dùng Class.getAnnotations() trên raw class của type argument để thay thế.** Một type-use annotation trên String trong field này thuộc **vị trí String ở field**, không phải annotation declaration của class java.lang.String và cũng không phải property vĩnh viễn của đối tượng String.class.

## 5. Ví dụ Java 17+ hoàn chỉnh: visitor có bảo vệ chu trình

Tạo tệp **AnnotatedTypeTreeDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedTypeVariable;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class AnnotatedTypeTreeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
    @interface Tag {
        String value();
    }

    static class Sample<
            @Tag("declaration") T extends @Tag("bound") Number> {

        @Tag("container")
        List<@Tag("element") String> names;

        List<@Tag("wildcard") ? extends @Tag("upper") Number> numbers;

        String @Tag("outer") [] @Tag("inner") [] matrix;

        List<@Tag("use-T") T> generic;
    }

    static String tags(AnnotatedType node) {
        List<String> values = new ArrayList<>();
        for (Tag tag : node.getAnnotationsByType(Tag.class)) {
            values.add(tag.value());
        }
        return values.isEmpty() ? "-" : String.join(",", values);
    }

    static String kind(AnnotatedType node) {
        if (node instanceof AnnotatedParameterizedType) {
            return "PARAMETERIZED";
        }
        if (node instanceof AnnotatedArrayType) {
            return "ARRAY";
        }
        if (node instanceof AnnotatedWildcardType) {
            return "WILDCARD";
        }
        if (node instanceof AnnotatedTypeVariable) {
            return "TYPE_VARIABLE";
        }
        return "CLASS";
    }

    static void walk(AnnotatedType node, String path,
                     Set<TypeVariable<?>> active) {
        System.out.println(path + " [" + kind(node)
                + "] @" + tags(node));

        AnnotatedType owner = node.getAnnotatedOwnerType();
        if (owner != null) {
            walk(owner, path + ".owner", active);
        }

        if (node instanceof AnnotatedParameterizedType p) {
            AnnotatedType[] args = p.getAnnotatedActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                walk(args[i], path + ".arg[" + i + "]", active);
            }
        } else if (node instanceof AnnotatedArrayType a) {
            walk(a.getAnnotatedGenericComponentType(),
                    path + ".component", active);
        } else if (node instanceof AnnotatedWildcardType w) {
            AnnotatedType[] upper = w.getAnnotatedUpperBounds();
            for (int i = 0; i < upper.length; i++) {
                walk(upper[i], path + ".upper[" + i + "]", active);
            }
            AnnotatedType[] lower = w.getAnnotatedLowerBounds();
            for (int i = 0; i < lower.length; i++) {
                walk(lower[i], path + ".lower[" + i + "]", active);
            }
        } else if (node instanceof AnnotatedTypeVariable tv) {
            TypeVariable<?> variable = (TypeVariable<?>) tv.getType();
            if (!active.add(variable)) {
                System.out.println(path + ".bounds [CYCLE]");
                return;
            }
            try {
                AnnotatedType[] bounds = tv.getAnnotatedBounds();
                for (int i = 0; i < bounds.length; i++) {
                    walk(bounds[i], path + ".bound[" + i + "]",
                            active);
                }
            } finally {
                active.remove(variable);
            }
        }
    }

    static void inspect(String fieldName) throws Exception {
        System.out.println("=== " + fieldName + " ===");
        AnnotatedType root =
                Sample.class.getDeclaredField(fieldName)
                        .getAnnotatedType();
        walk(root, "field", new HashSet<>());
    }

    public static void main(String[] args) throws Exception {
        inspect("names");
        inspect("numbers");
        inspect("matrix");
        inspect("generic");

        TypeVariable<?> declared =
                Sample.class.getTypeParameters()[0];
        System.out.print("T declaration @");
        Tag tag = declared.getAnnotation(Tag.class);
        System.out.println(tag == null ? "-" : tag.value());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp với JDK 17 trở lên:

~~~bash
javac AnnotatedTypeTreeDemo.java
java AnnotatedTypeTreeDemo
~~~

**Stdout dự kiến theo API chuẩn của Java 17+:**

~~~text
=== names ===
field [PARAMETERIZED] @container
field.arg[0] [CLASS] @element
=== numbers ===
field [PARAMETERIZED] @-
field.arg[0] [WILDCARD] @wildcard
field.arg[0].upper[0] [CLASS] @upper
=== matrix ===
field [ARRAY] @outer
field.component [ARRAY] @inner
field.component.component [CLASS] @-
=== generic ===
field [PARAMETERIZED] @-
field.arg[0] [TYPE_VARIABLE] @use-T
field.arg[0].bound[0] [CLASS] @bound
T declaration @declaration
~~~

Đường dẫn không dùng tên lớp triển khai nội bộ của JVM, vì visitor tự phân loại thông qua các interface Reflection. Trong ví dụ, tất cả field đều được khai báo trực tiếp trong Sample nên getDeclaredField(...) phù hợp.

### Giải thích field names

Khai báo **@Tag("container") List<@Tag("element") String> names** tạo hai vị trí riêng:

- **field** là List<String> và mang annotation container.
- **field.arg[0]** là String và mang annotation element.

Nếu chỉ gọi Field.getAnnotations(), bạn không dựng được đường đi này. Nếu chỉ nhìn GenericType, bạn biết có String nhưng mất annotation tại vị trí sử dụng.

### Giải thích field numbers

Khai báo **List<@Tag("wildcard") ? extends @Tag("upper") Number>** gồm:

- Node List, bản thân không có Tag.
- Node wildcard là đối số generic thứ nhất, mang Tag wildcard.
- Upper bound Number của wildcard, mang Tag upper.

Truy cập wildcard bằng AnnotatedWildcardType; **upper bound** lấy từ getAnnotatedUpperBounds(). Nếu dùng **? super Integer**, phải đi vào **getAnnotatedLowerBounds()** và biểu thị nhánh lower; nếu chỉ duyệt upper, bạn sẽ mất annotation của lower bound.

### Giải thích field matrix

Với **String @Tag("outer") [] @Tag("inner") []**, hai cặp ngoặc vuông thuộc hai tầng array khác nhau. Reflection biểu diễn bằng **hai AnnotatedArrayType**:

- field: outer dimension mang Tag outer.
- field.component: inner dimension mang Tag inner.
- field.component.component: component class String, trong ví dụ không có Tag.

Nếu bạn nối các annotation thành danh sách chung [outer, inner], không còn biết mỗi nhãn thuộc chiều nào. Khi xử lý mảng nhiều chiều hoặc type-use validation trên từng chiều, sự khác biệt này có ý nghĩa.

### Giải thích field generic và type parameter T

Field **List<@Tag("use-T") T> generic** có một argument là AnnotatedTypeVariable. Annotation use-T gắn trên **vị trí sử dụng T trong List**, khác với:

- **@Tag("declaration")** gắn trên **khai báo type parameter T** của Sample, đọc qua TypeVariable.getAnnotation(Tag.class).
- **@Tag("bound")** gắn trên **bound Number** của T, đọc qua AnnotatedTypeVariable.getAnnotatedBounds() hoặc TypeVariable.getAnnotatedBounds().

Ba nguồn annotation đều liên quan T, nhưng **không nằm cùng một node**. Một công cụ tổng quát có thể lưu phần declaration ở record riêng thay vì đưa vào cây field.

## 6. Tránh đệ quy vô hạn khi duyệt type variable

Một generic bound có thể tự tham chiếu:

~~~java
class Node<T extends Comparable<T>> {
    T value;
}
~~~

Nếu visitor mở rộng T, rồi Comparable<T>, rồi argument T, lại mở rộng bound Comparable<T> liên tục, nó sẽ không dừng:

~~~text
T
└── bound[0] Comparable<T>
    └── arg[0] T
        └── bound[0] Comparable<T>
            └── ...
~~~

Ví dụ chính dùng **Set<TypeVariable<?>> active** để ghi nhớ các type variable đang nằm trên nhánh duyệt hiện tại. Khi gặp lại một biến đang active, visitor in marker **[CYCLE]** thay vì mở rộng bounds vô hạn.

Kỹ thuật này có hai đặc điểm quan trọng:

1. Visitor **vẫn xuất node occurrence hiện tại** trước khi phát hiện vòng lặp ở khâu mở rộng bounds, nên annotation gắn tại occurrence đó không bị mất.
2. Dùng **finally** để xóa type variable khỏi tập active sau khi duyệt nhánh xong. Một T xuất hiện trên nhánh độc lập khác vẫn được duyệt đầy đủ; không được bỏ qua chỉ vì đã gặp T trước đó trong toàn bộ chương trình.

Một resolver phức tạp có thể dùng cache theo cặp (generic declaration, type-variable binding), node identity và giới hạn độ sâu. Nhưng phải có phương án xử lý chu trình trong cây type bounds; không được lặp không giới hạn.

## 7. Owner type và nested generic types

Nested class có thể mang type-use annotation trên **outer owner**, **inner type** và **type argument của inner**. Ví dụ minh họa:

~~~java
class Outer {
    class Inner<U> {}
}

// Đặt sau khai báo Tag có TYPE_USE target và trong một class hợp lệ:
@Tag("owner") Outer.@Tag("inner") Inner<@Tag("argument") String> ref;
~~~

Cách biểu diễn vị trí đúng:

~~~text
field             -> annotation inner, trên Inner<String>
field.owner       -> annotation owner, trên Outer
field.arg[0]      -> annotation argument, trên String
~~~

Trong Java 9+, **AnnotatedType.getAnnotatedOwnerType()** cho phép visitor truy cập owner nếu tồn tại. Tên kiểu có dấu chấm không phải là phương pháp đủ để xác định owner annotations. Không thể lấy annotation của Outer bằng cách gán nó cho Inner cho tiện.

**Không phải node nào cũng có owner**. getAnnotatedOwnerType() có thể trả null. Cấu trúc của top-level class, static nested class, inner class và parameterized owner có thể khác nhau. Visitor phải duyệt theo metadata thực tế, không tự tạo owner nhân tạo.

Với owner chứa generic arguments, nhánh owner cũng có thể là AnnotatedParameterizedType và phải được duyệt đệ quy; nếu không, annotation của type arguments ở outer type sẽ biến mất.

## 8. Các root khác ngoài Field

Để áp dụng trình duyệt cho một class toàn diện, bạn có thể gọi cùng hàm walk(...) từ nhiều nguồn:

| Nơi khai báo | API trả AnnotatedType hoặc mảng AnnotatedType |
|---|---|
| Field | Field.getAnnotatedType() |
| Method return | Method.getAnnotatedReturnType() |
| Method parameters | Method.getAnnotatedParameterTypes() |
| Constructor parameters | Constructor.getAnnotatedParameterTypes() |
| Method/constructor throws | Executable.getAnnotatedExceptionTypes() |
| Superclass | Class.getAnnotatedSuperclass() |
| Implemented interfaces | Class.getAnnotatedInterfaces() |
| Type parameter bounds | TypeVariable.getAnnotatedBounds() |

Chẳng hạn:

~~~java
class Service {
    public java.util.List<@Tag("returned") String> read(
            java.util.List<@Tag("input") String> values) {
        return values;
    }
}
~~~

Đây là ví dụ class minh họa, cần Tag với TYPE_USE và RUNTIME retention. Với:

~~~java
Method m = Service.class.getMethod("read", java.util.List.class);
AnnotatedType out = m.getAnnotatedReturnType();
AnnotatedType in = m.getAnnotatedParameterTypes()[0];
~~~

Bạn có thể gọi **walk(out, "return", active)** và **walk(in, "parameter[0]", active)**. Annotation returned nằm ở **return.arg[0]**, còn input nằm ở **parameter[0].arg[0]**. Dù cả hai đều là List<String>, chúng là hai **vị trí khai báo khác nhau**.

Cả hai đoạn là phần minh họa, không nằm trong file chương trình chạy độc lập ở mục 5; khi đưa vào chương trình phải thêm import Method/AnnotatedType và xử lý NoSuchMethodException.

### Lưu ý về annotation trên constructor

Constructor không có return value theo cú pháp như một method, nhưng Reflection có **Constructor.getAnnotatedReturnType()** phục vụ metadata được Java API định nghĩa cho constructor. Đừng tự gán nó thành return value của một method thông thường. Các tham số và exception types của constructor vẫn là những root thông dụng hơn khi phân tích annotation trên kiểu.

## 9. Dữ liệu đầu ra nên là cây, không phải tập annotation phẳng

Một công cụ sinh schema có thể lưu:

~~~json
{
  "path": "field.arg[0].upper[0]",
  "kind": "CLASS",
  "typeName": "java.lang.Number",
  "annotations": [
    {"name": "Tag", "value": "upper"}
  ]
}
~~~

Đây là minh họa một node JSON; không phải một object có thể xây đầy đủ chỉ bằng gọi Class.getAnnotations(). Annotation và value phải lấy ở node AnnotatedType tại path tương ứng.

Nếu cần hiển thị trực quan, có thể hiển thị cây bằng thụt dòng; tuy nhiên lưu cả **path ổn định** giúp unit test, so sánh schema và trỏ lỗi chính xác. Với nhiều root, thêm source identifier như field name, method signature hoặc parameter index.

Để export sang JSON một cách thực tế, nên định nghĩa cấu trúc bản ghi rõ ràng, ví dụ:

~~~java
record TypeUseLocation(
        String source,
        String path,
        String kind,
        String typeName,
        java.util.List<String> annotationNames) {}
~~~

Không chỉ serialize một List<Annotation> vì như thế mọi vị trí con bị mất.

## 10. Repeatable annotations và multiple annotations

Java cho phép annotation có target TYPE_USE được khai báo **@Repeatable**, trong trường hợp ấy một node có thể chứa nhiều annotation cùng loại. Visitor có thể dùng **getAnnotationsByType(Tag.class)** khi muốn các instance logic của một annotation cụ thể, kể cả trường hợp được nhóm trong repeatable container.

Nếu viết trình duyệt tổng quát không biết trước Tag là gì, hãy đọc **getDeclaredAnnotations()** của từng AnnotatedType, rồi tùy nhu cầu xử lý/giải nén repeatable containers theo metadata chuẩn. Không nên gộp annotations có cùng tên tại hai **node khác nhau**; việc có cùng loại annotation không biến hai vị trí thành một.

Nếu công cụ cần output ổn định giữa các lần chạy, sắp xếp annotations theo tên đầy đủ và giá trị attributes thay vì dựa vào thứ tự ngẫu nhiên. Thứ tự **nhánh cây** phải được quyết định bằng argument index, array component, bound index và owner relation.

## 11. Các giới hạn quan trọng

**Reflection metadata không thay validation.** Annotation có tên @NotNull hoặc @Tag("element") không tự kiểm tra object trong runtime list. Framework cần logic validation của mình, đặc biệt với nested generics.

**Type erasure vẫn tồn tại.** Một AnnotatedTypeVariable T không biết ngay concrete type parameter của object thực tế. Nếu class Derived extends Base<String>, muốn thay T bằng String trong field khai báo ở Base phải phân giải generic type bindings theo hierarchy, đồng thời bảo toàn các annotation theo đúng các vị trí tương ứng. Đây là bước khác với việc chỉ duyệt AnnotatedType.

**Không giả định mọi Type là Class.** AnnotatedParameterizedType có Type là ParameterizedType; wildcard, type variable và generic array đều có cấu trúc khác nhau. Cast mù node.getType() thành Class<?> có thể gây ClassCastException.

**Ranh giới module và access.** Truy xuất metadata không tự đồng nghĩa được phép đọc private field value hay gọi private method. Nếu công cụ đi xa hơn việc duyệt kiểu, Field.get(), Method.invoke(), Constructor.newInstance() và setAccessible() có các kiểm tra access/JPMS riêng.

**Annotation không có RUNTIME retention** không hiện qua core Reflection tương ứng. Kết luận “không thấy qua visitor” chỉ có nghĩa “không có metadata runtime-visible tại vị trí ấy”, không chứng minh source chưa từng có annotation.

**Array dimensions** có annotation riêng, không được nối chúng lên component type.

**Wildcards** có thể có upper bound hoặc lower bound; phân biệt .upper và .lower.

**TypeVariable declaration** khác occurrence: annotation TYPE_PARAMETER trên khai báo và TYPE_USE ở mỗi vị trí sử dụng T không cùng một nguồn.

**Đường dẫn phải giữ quan hệ từ root**. Nếu hai field cùng chứa annotation @Tag("element") trên String, các annotation ấy thuộc hai vị trí khai báo khác nhau và cần source identifier khác nhau.

## 12. Các lỗi thường gặp

1. **Duyệt duy nhất Type.getTypeName()** rồi cố suy ra annotation từ chữ: không có dữ liệu vị trí type-use.
2. **Chỉ đọc Field.getAnnotations()**: bỏ sót annotation trong generic arguments, wildcard bounds hoặc array dimensions.
3. **Gộp annotation của List và String** thành một danh sách: sai node sở hữu annotation.
4. **Không duyệt AnnotatedParameterizedType**: bỏ qua annotation ở nested generic arguments.
5. **Không duyệt AnnotatedArrayType theo từng tầng**: mất annotation ở từng chiều array.
6. **Duyệt wildcard nhưng bỏ qua upper/lower bounds**: mất annotation hoặc nhầm phương sai.
7. **Coi TypeVariable.getBounds() là đủ**: lấy Type thuần có thể mất annotation trên bound; dùng getAnnotatedBounds().
8. **Coi annotation declaration của T là annotation trên mọi use-site T**: hai loại metadata khác nhau.
9. **Không có cycle detection cho T extends Comparable<T>**: visitor có thể chạy vô hạn.
10. **Bỏ qua getAnnotatedOwnerType()**: annotation trên owner của nested class bị mất.
11. **Bỏ qua RetentionPolicy.RUNTIME**: không hiểu vì sao Reflection không thấy annotation ở source.
12. **Tạo JSON chỉ chứa tên annotations**: mất vị trí và không thể tái tạo semantic type-use.
13. **Dùng class runtime của phần tử collection để tìm type-use annotations**: dữ liệu runtime không phải metadata kiểu khai báo.
14. **Xóa annotations khi thay generic type variables**: có thể làm mất thông tin schema/validation.
15. **Tin rằng thấy annotation nghĩa là runtime đã tự validate**: annotation chỉ là mô tả; validation là cơ chế riêng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Với Map<@A String, List<@B Integer>>, nếu root là field thì @B nằm ở đâu?

**Đáp án:** Ở **field.arg[1].arg[0]**. Trước tiên đi vào type argument thứ hai của Map, sau đó type argument thứ nhất của List.

**Câu 2.** Với List<@A ? extends @B Number>, @A và @B có cùng một node không?

**Đáp án:** Không. @A nằm ở **field.arg[0]** (wildcard), @B ở **field.arg[0].upper[0]** (bound Number).

**Câu 3.** Với String @A [] @B [], cần duyệt những nhánh nào?

**Đáp án:** Root là AnnotatedArrayType cho chiều ngoài @A; component là AnnotatedArrayType cho chiều trong @B; component tiếp theo là String.

**Câu 4.** Với class Box<@A T extends @B Number> { List<@C T> items; }, ba annotation thuộc đâu?

**Đáp án:** @A trên type-parameter declaration T; @B trên bound Number của T; @C trên vị trí dùng T trong List. Không được gộp.

**Câu 5.** Vì sao visitor cần Set<TypeVariable<?>> active?

**Đáp án:** Để chặn việc mở rộng bounds vô hạn trong cấu trúc tự tham chiếu như T extends Comparable<T>, nhưng vẫn cho phép cùng T xuất hiện hợp lệ ở nhánh khác.

**Câu 6.** Nếu một annotation có retention CLASS, visitor runtime có đảm bảo thấy nó không?

**Đáp án:** Không. Core Reflection chỉ trình bày runtime-visible annotations; phải dùng công cụ đọc class file nếu cần dữ liệu không runtime-visible.

**Câu 7.** Muốn đọc annotation trên method return và trên argument của method parameter thì dùng API nào?

**Đáp án:** Method.getAnnotatedReturnType() và Method.getAnnotatedParameterTypes()[i], sau đó duyệt mỗi root với đường dẫn khác nhau để không trộn vị trí.

## Tài liệu chuẩn

- Java SE API: java.lang.reflect.AnnotatedType, AnnotatedParameterizedType, AnnotatedArrayType, AnnotatedWildcardType, AnnotatedTypeVariable.
- Java SE API: Field.getAnnotatedType(), Method.getAnnotatedReturnType(), Executable.getAnnotatedParameterTypes(), Executable.getAnnotatedExceptionTypes().
- Java SE API: TypeVariable.getAnnotatedBounds(), AnnotatedElement.getAnnotationsByType(), Class.getAnnotatedSuperclass(), Class.getAnnotatedInterfaces().
- Java Language Specification: type-use positions, generic type parameters, annotation targets, annotation retention và recursive bounds.
- Java Virtual Machine Specification: runtime-visible type annotations và metadata class file, khi cần hiểu cơ chế lưu vị trí.

**Ghi nhớ:** trình duyệt cây kiểu phải lấy **AnnotatedType làm điểm khởi đầu**, ghi **annotation ngay tại node hiện tại**, đi tiếp theo các cạnh **arg / component / upper / lower / bound / owner**, đồng thời đánh dấu nguồn declaration và bảo vệ khỏi chu trình. Chỉ như vậy annotation mới được bảo toàn đúng **vị trí** thay vì biến thành tập tên không còn ngữ cảnh.