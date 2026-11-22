# Sắp xếp metadata Reflection để đầu ra có thứ tự ổn định

## 1. Vì sao cần sắp xếp metadata?

Công cụ sinh tài liệu, schema hay snapshot thường cần đầu ra lặp lại được. Tuy nhiên các mảng member từ `getDeclaredMethods()`, `getDeclaredFields()` và nhiều API Reflection khác **không cam kết thứ tự**. Hai lần sinh có thể cho danh sách giống nhau nhưng thứ tự khác, khiến bản diff báo nhầm thay đổi.

Đây là bài về **canonical output**: trước hết chọn đúng tập member, sau đó sắp xếp theo khóa đủ phân biệt overload, chuẩn hóa định dạng/encoding và bảo toàn những thứ tự có ngữ nghĩa (ví dụ vị trí tham số hay thứ tự thực thi được cấu hình). Sort metadata hiển thị **không tự xác định** thứ tự chạy các method.

## 2. Reflection trả về tập thành viên, không phải thứ tự trình bày

Các API nên phân biệt:

| API | Loại metadata | Phạm vi và điểm cần nhớ |
| --- | --- | --- |
| `getDeclaredFields()` | `Field[]` | Field khai báo ngay trong lớp, gồm cả non-public; không gồm field kế thừa |
| `getFields()` | `Field[]` | Field `public` nhìn thấy theo quy tắc Reflection, có thể gồm field kế thừa |
| `getDeclaredMethods()` | `Method[]` | Method khai báo ngay trong lớp, có thể gồm bridge/synthetic; không gồm method kế thừa |
| `getMethods()` | `Method[]` | Các method `public` của lớp/interface và method kế thừa theo quy tắc API |
| `getDeclaredConstructors()` | `Constructor<?>[]` | Constructor khai báo trong lớp; constructor không được kế thừa |
| `getInterfaces()` | `Class<?>[]` | Interface **trực tiếp** của lớp; Java phản ánh thứ tự khai báo, nhưng công cụ cần canonical order có thể chọn sort |
| `getDeclaredClasses()` | `Class<?>[]` | Các lớp/interface thành viên được khai báo, không bao gồm mọi lớp local/anonymous |
| `getDeclaredAnnotations()` | `Annotation[]` | Annotation khai báo trực tiếp, chịu quy tắc của Annotation API |

**Không phải mọi thông tin đều vô thứ tự:** chẳng hạn danh sách kiểu tham số trong chữ ký method và constructor phải giữ **đúng thứ tự khai báo**, vì `f(int, String)` khác `f(String, int)`. Khi muốn sắp xếp **các phương thức**, chỉ thay vị trí của *các bản ghi method*, không đảo các parameter bên trong từng chữ ký.

Đối với `getInterfaces()`, Java Reflection ghi nhận thứ tự interface trong phần `implements` / `extends`; nếu mục đích là báo lại cấu trúc source, có thể giữ thứ tự này. Nếu mục đích là so sánh *tập interface* không xét thứ tự khai báo, có thể sort theo tên như một quy tắc thiết kế của công cụ. **Chỉ sắp xếp khi ngữ nghĩa của dữ liệu cho phép.**

## 3. Quy tắc thiết kế khóa sắp xếp ổn định

Một bộ so sánh (comparator) tốt có ba đặc tính:

1. **Được xác định rõ:** key tạo từ metadata có nội dung ổn định trong cùng phạm vi đầu vào, ví dụ `Field.getName()`, `Method.getName()` và các kiểu tham số.
2. **Đủ phân biệt:** thêm khóa phụ nếu khóa đầu có thể trùng. Đặc biệt, tên phương thức **không đủ** vì Java cho phép overload.
3. **Có chính sách rõ về trường hợp còn trùng:** nếu hai mục xuất có cùng khóa, cần xác định chúng thực sự tương đương khi xuất hay bổ sung khóa phân biệt; đừng âm thầm dựa vào thứ tự mảng đầu vào.

Một lựa chọn thông dụng khi trình bày:

| Metadata | Khóa sắp xếp gợi ý | Lý do |
| --- | --- | --- |
| Field trong một lớp | tên → kiểu field → lớp khai báo | Tên dễ tìm; bổ sung khóa khi gộp nhiều lớp |
| Method | tên → danh sách **kiểu tham số có thứ tự** → kiểu trả về → lớp khai báo | Phân biệt overload và trường hợp bridge/covariant return |
| Constructor | danh sách kiểu tham số có thứ tự → lớp khai báo | Constructor không có tên riêng cho từng overload |
| Class hoặc interface | tên nhị phân (`Class.getName()`) | Dễ so sánh có phân biệt package và dạng tên lồng nhau |
| Annotation (khi chỉ liệt kê các loại) | tên kiểu annotation | Không phụ thuộc thứ tự mảng annotation |
| Tham số **bên trong** một method | giữ thứ tự gốc | Thứ tự tham số là thành phần của chữ ký |

### 3.1. Vì sao dùng `Class.getName()` trong khóa kỹ thuật?

`Class.getName()` cung cấp tên nhị phân với kiểu tham chiếu (ví dụ `java.util.Map$Entry`), và dạng được mã hóa với mảng (ví dụ `[Ljava.lang.String;`). Trong một phạm vi class loader xác định, nó phù hợp để xây key nhất quán. `Class.getSimpleName()` thì dễ trùng giữa các package; `getCanonicalName()` có thể trả `null` với lớp local/anonymous.

Khi **hiển thị cho người học/người dùng**, có thể dùng `Class.getTypeName()` để có dạng dễ đọc như `java.lang.String[]`. Nên **tách khóa kỹ thuật và chuỗi hiển thị**, tránh sửa cách sắp xếp chỉ vì định dạng giao diện thay đổi.

Hai đối tượng `Class` có cùng tên nhưng được **định nghĩa bởi hai class loader khác nhau** vẫn là hai kiểu runtime khác nhau. Nếu công cụ gộp dữ liệu của nhiều loader, chỉ dùng `getName()` không đủ để định danh toàn cục; cần cung cấp một **định danh namespace/loader ổn định từ cấu hình của công cụ**, không dùng `ClassLoader.toString()` hay `System.identityHashCode(...)` như khóa xuất tái lập giữa các lần chạy.

### 3.2. Vì sao method cần nhiều tiêu chí?

Một lớp có thể khai báo:

~~~java
void print(int number) {}
void print(String text) {}
~~~

Nếu chỉ dùng `Comparator.comparing(Method::getName)`, hai method đều có khóa `print`. Java `Arrays.sort(Object[], comparator)` là một phép sort ổn định: các phần tử có comparator kết quả `0` giữ thứ tự tương đối của input. Nhưng **input lấy từ Reflection vốn không được bảo đảm thứ tự**. Do đó kết quả vẫn không thể tái lập tuyệt đối.

Khóa gồm `getName()` + `getParameterTypes()` theo **thứ tự tham số** sẽ phân biệt hai overload. Thêm `getReturnType()` giúp phân biệt metadata liên quan bridge method hoặc kiểu trả về hiệp biến trong bytecode, vì JVM có thể có các method cùng tên/tham số nhưng khác return type, dù source Java không cho khai báo overload chỉ bằng return type. Khi gộp từ nhiều lớp, thêm `getDeclaringClass()`. Nếu bản ghi thực sự còn trùng khóa và bạn vẫn muốn xuất cả hai, phải thiết kế thêm bước canonical hóa/deduplication theo mục tiêu.

## 4. Ví dụ hoàn chỉnh Java 17+: sắp xếp field, method, constructor

Chương trình minh họa một lớp chứa field không theo thứ tự bảng chữ cái, method overload và nhiều constructor. Chúng ta **không in mảng Reflection thô** rồi suy đoán thứ tự. Thay vào đó dùng `Comparator` và chỉ in các bản ghi đã sort.

Tạo tệp **`StableReflectionReport.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class StableReflectionReport {
    public static class Sample {
        private int zeta;
        private String alpha;

        public Sample() {}

        public Sample(int initial) {
            zeta = initial;
        }

        public void ping() {}

        public String transform(String value) {
            return value;
        }

        public int transform(int value) {
            return value * 2;
        }
    }

    static String parameterKey(Class<?>[] parameterTypes) {
        return Arrays.stream(parameterTypes)
                .map(Class::getName)
                .collect(Collectors.joining(","));
    }

    static String parameterDisplay(Class<?>[] parameterTypes) {
        return Arrays.stream(parameterTypes)
                .map(Class::getTypeName)
                .collect(Collectors.joining(", "));
    }

    static final Comparator<Field> FIELD_ORDER =
            Comparator.comparing(Field::getName)
                    .thenComparing(f -> f.getType().getName())
                    .thenComparing(f -> f.getDeclaringClass().getName());

    static final Comparator<Method> METHOD_ORDER =
            Comparator.comparing(Method::getName)
                    .thenComparing(m -> parameterKey(m.getParameterTypes()))
                    .thenComparing(m -> m.getReturnType().getName())
                    .thenComparing(m -> m.getDeclaringClass().getName());

    static final Comparator<Constructor<?>> CONSTRUCTOR_ORDER =
            Comparator.<Constructor<?>, String>comparing(
                    c -> parameterKey(c.getParameterTypes()))
                    .thenComparing(c -> c.getDeclaringClass().getName());

    public static void main(String[] args) {
        Field[] fields = Sample.class.getDeclaredFields();
        Arrays.sort(fields, FIELD_ORDER);

        Method[] methods = Sample.class.getDeclaredMethods();
        Arrays.sort(methods, METHOD_ORDER);

        Constructor<?>[] constructors = Sample.class.getDeclaredConstructors();
        Arrays.sort(constructors, CONSTRUCTOR_ORDER);

        System.out.println("Fields:");
        for (Field field : fields) {
            System.out.println("  " + field.getName()
                    + ": " + field.getType().getTypeName());
        }

        System.out.println("Methods:");
        for (Method method : methods) {
            System.out.println("  " + method.getName() + "("
                    + parameterDisplay(method.getParameterTypes()) + ") -> "
                    + method.getReturnType().getTypeName());
        }

        System.out.println("Constructors:");
        for (Constructor<?> constructor : constructors) {
            System.out.println("  Sample("
                    + parameterDisplay(constructor.getParameterTypes()) + ")");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac StableReflectionReport.java
java StableReflectionReport
~~~

Kết quả:

~~~text
Fields:
  alpha: java.lang.String
  zeta: int
Methods:
  ping() -> void
  transform(int) -> int
  transform(java.lang.String) -> java.lang.String
Constructors:
  Sample()
  Sample(int)
~~~

**Giải thích:**

- `getDeclaredFields()`, `getDeclaredMethods()` và `getDeclaredConstructors()` là nguồn dữ liệu. Không trông chờ thứ tự mà chúng trả về.
- `Arrays.sort(fields, FIELD_ORDER)` đặt `alpha` trước `zeta`; `FIELD_ORDER` có khóa phụ là kiểu và lớp khai báo để có thể tái sử dụng cùng chính sách khi mở rộng bộ xuất.
- `METHOD_ORDER` đặt `ping` trước `transform`; hai overload `transform` được phân biệt nhờ **kiểu tham số**, nên `transform(int)` đứng trước `transform(String)` theo so sánh chuỗi tên kiểu.
- `CONSTRUCTOR_ORDER` so sánh danh sách tham số, trong đó chuỗi rỗng cho constructor không tham số xếp trước `int`.
- Dạng tên trong đầu ra dùng `getTypeName()` để người đọc dễ hiểu, còn comparator dùng `getName()` như key.
- Sort chỉ sắp xếp các **mảng `Field[]` / `Method[]` / `Constructor[]`** vừa lấy ra để xuất; không thay đổi thứ tự thành viên trong bytecode hay cách JVM gọi method.

Ví dụ giữ mọi method được khai báo trong lớp `Sample`. Trong công cụ thực tế cần một chính sách rõ về `private`, `public`, `synthetic` hoặc `bridge` trước khi sắp xếp.

## 5. Từ khóa sắp xếp đến đầu ra có thể tái lập

Thứ tự metadata là một phần của bài toán, nhưng pipeline xuất báo cáo cần xác định đủ các bước:

~~~text
Chọn đối tượng Class/nguồn dữ liệu
              ↓
Khám phá metadata đúng phạm vi
              ↓
Lọc/canonical hóa theo chính sách
              ↓
Tạo khóa sắp xếp có tiêu chí phụ
              ↓
Sort các bản ghi sẽ xuất
              ↓
Định dạng thống nhất (kiểu, annotation, ký tự)
              ↓
Ghi đầu ra với encoding/newline thống nhất
              ↓
So sánh snapshot hoặc tạo tài liệu
~~~

### 5.1. Chọn phạm vi trước khi sort

Câu hỏi đầu tiên là **công cụ cần khai báo của lớp hay API public nhìn thấy được?**

- `getDeclaredMethods()` thích hợp khi kiểm tra điều gì được khai báo **trực tiếp** trong lớp, kể cả private method và bridge/synthetic metadata.
- `getMethods()` thích hợp hơn khi trình bày các method `public` có thể nhìn thấy, kể cả kế thừa.
- Nếu muốn xem một hệ phân cấp có tính đến method `private` của superclass, phải duyệt superclass theo chính sách riêng; `getDeclaredMethods()` trên lớp con không tự đưa chúng vào.

Hai tập metadata khác nhau có thể có thứ tự ổn định nhưng **đầu ra mang ngữ nghĩa khác nhau**. Sort không bù được cho việc chọn sai tập nguồn.

### 5.2. Lọc bridge và synthetic với sự thận trọng

Compiler có thể tạo **bridge method** để phục vụ generics/covariant returns, và một số class có synthetic member. `Method.isBridge()` và `Method.isSynthetic()` giúp phát hiện các trường hợp đó:

~~~java
Method[] visible = Arrays.stream(type.getDeclaredMethods())
        .filter(m -> !m.isSynthetic() && !m.isBridge())
        .sorted(METHOD_ORDER)
        .toArray(Method[]::new);
~~~

*Đây là fragment giả định có `Class<?> type` và comparator `METHOD_ORDER` như ví dụ mục 4.*

Bộ lọc trên hữu ích nếu muốn tài liệu gần với **API mà lập trình viên thường chủ động viết**. Nhưng đối với công cụ kiểm tra bytecode, phân tích quá trình dispatch hoặc nghiên cứu generic bridge, việc loại bridge/synthetic sẽ **làm mất thông tin cần thiết**. Quyết định lọc phải gắn với mục đích, không dùng như công thức bắt buộc.

Đừng dựa vào `Method.toString()` hoặc `toGenericString()` làm khóa duy nhất khi bạn cần định danh có cấu trúc, vì định dạng hiển thị có thể thay đổi theo phiên bản/chi tiết API. Hãy truy xuất các thành phần bằng getter rồi tự xác định canonical representation.

### 5.3. Metadata generic và annotation

`Method.getParameterTypes()` cho các `Class<?>` sau khi xét erasure; `getGenericParameterTypes()` và `getGenericReturnType()` có thể biểu diễn `ParameterizedType`, `TypeVariable` hoặc `GenericArrayType`.

- Nếu mục đích là **khóa lời gọi runtime/JVM**, dùng các kiểu tham số đã erasure thường phù hợp.
- Nếu mục đích là **tạo tài liệu generic chính xác**, đưa thông tin generic vào **phần hiển thị**, và nếu cần so sánh thay đổi generic thì bổ sung cách chuẩn hóa `Type` để phân biệt.
- Khi xử lý annotation, việc chỉ sort các annotation theo `annotationType().getName()` có thể đủ cho bảng **liệt kê các loại annotation**. Nếu xuất cả giá trị phần tử annotation, cần canonical hóa giá trị theo tên phần tử; với array value phải giữ thứ tự có ngữ nghĩa. Không dựa vào chuỗi `annotation.toString()` như giao thức xuất dữ liệu ổn định.
- `Class.getDeclaredAnnotations()` khác `getAnnotations()` ở phạm vi kế thừa; trước khi sắp xếp phải quyết định có lấy annotation kế thừa theo `@Inherited` hay không.

Đối với cùng một annotation có nhiều phần tử (*elements*), các phương thức mô tả element được Reflection trả về trong mảng không cam kết thứ tự. Có thể sắp xếp `annotation.annotationType().getDeclaredMethods()` theo `Method.getName()` trước khi xuất tên và giá trị. Cần xử lý các giá trị là `Class`, enum, annotation lồng, mảng và kiểu primitive bằng quy tắc riêng để tránh ghi ra giá trị không chuẩn hóa.

## 6. Khi dữ liệu gồm nhiều lớp hoặc nhiều module

Một chương trình quét nhiều lớp rồi lấy metadata từ từng lớp cần ổn định **cả danh sách lớp đầu vào** lẫn metadata của từng lớp:

~~~java
List<Class<?>> orderedTypes = classes.stream()
        .sorted(Comparator.comparing(Class::getName))
        .toList();
~~~

*Fragment giả định `classes` là `Collection<Class<?>>` và đã có import của `List` / `Comparator`.*

Nếu danh sách lớp đến từ quét classpath, quét directory, ZIP/JAR hay `ServiceLoader`, thứ tự nguồn ban đầu có thể phụ thuộc môi trường. Hãy xác định rõ chính sách chọn lớp và sort tập đầu vào nếu thứ tự không có ý nghĩa nghiệp vụ. Nhưng **không** được tự thay đổi thứ tự có ý nghĩa, chẳng hạn các bộ xử lý thực thi theo priority, các bước migration hoặc danh sách handler yêu cầu precedence. Ổn định thứ tự tài liệu và ổn định thứ tự **thực thi** là hai mục tiêu khác nhau.

Đối với các module trong JPMS, có thể cần cùng với `Class.getName()` một định danh module ổn định (ví dụ tên module được khai báo, nếu có). Trong mô hình nhiều class loader, phải ghi thêm định danh *namespace* do chính hệ thống của bạn cấp và duy trì qua lần chạy. Một mô tả module/classloader **chỉ dựa trên địa chỉ đối tượng** hoặc thứ tự loader được tạo thường không ổn định cho snapshot.

Khi xuất thành danh sách JSON, thứ tự phần tử array là quan sát được nên nên xuất theo thứ tự đã định. Với object/map, cần quy định cách canonical hóa tên key nếu phụ thuộc vào thứ tự serialize; không mặc định mọi serializer hay mọi map giữ cùng thứ tự. Ví dụ dùng `TreeMap` với comparator xác định để quản lý key khi ngữ nghĩa cho phép, hoặc dùng một serializer hỗ trợ canonical output.

## 7. Những nguyên nhân khiến snapshot vẫn thay đổi sau khi sort

Sort metadata giúp loại bỏ khác biệt do thứ tự duyệt. Nó **không đảm bảo** đầu ra byte-for-byte giống nhau khi các yếu tố khác đã thay đổi:

| Nguồn biến động | Cách xử lý |
| --- | --- |
| Khác JDK/compiler làm phát sinh bridge/synthetic khác | Quy định môi trường xây dựng, chính sách lọc/hiển thị và phạm vi so sánh |
| Dữ liệu quét classpath/JAR đầu vào khác | Cố định nguồn dữ liệu và sort danh sách class khi phù hợp |
| `hashCode`, `identityHashCode`, `toString` của loader/đối tượng | Không sử dụng để định danh xuất báo cáo |
| Timestamp, đường dẫn tuyệt đối, UUID ngẫu nhiên | Bỏ khỏi phần dữ liệu canonical hoặc chuẩn hóa theo yêu cầu |
| Format chịu `Locale.getDefault()` | Dùng định dạng độc lập locale hoặc chỉ rõ `Locale.ROOT` khi thích hợp |
| Charset mặc định, CRLF/LF, dấu xuống dòng cuối | Ghi UTF-8 và quy định newline nhất quán |
| Annotation có mảng hoặc giá trị lồng nhau | Giữ thứ tự có ngữ nghĩa, chuẩn hóa key và cách serialize |
| Cùng tên class nhưng khác class loader | Bổ sung namespace ID ổn định khi hệ thống cần phân biệt |
| Thay đổi thực sự trong API, annotation, method signature | **Giữ lại để diff phát hiện**, không làm mất bằng sort |

Ví dụ khi ghi file một báo cáo đã chuẩn hóa:

~~~java
Files.writeString(
        outputPath,
        report.replace("\r\n", "\n"),
        StandardCharsets.UTF_8);
~~~

*Fragment cần import `java.nio.file.Files` và `java.nio.charset.StandardCharsets`; `outputPath` là `Path` và `report` là `String` đã được định nghĩa. Với quy trình cần chuẩn hóa mọi dạng newline, xử lý cả `\r` đơn lẻ tùy nguồn dữ liệu.*

Quy định cả **trailing newline** và encoding trong hợp đồng xuất sẽ giảm những diff không liên quan nội dung. Nếu báo cáo là định dạng dùng lâu dài, hãy công bố version của quy tắc xuất; đổi key sort là đổi hành vi tiêu thụ dữ liệu dù API Java bên dưới không đổi.

## 8. Kiểm tra tính ổn định một cách có ý nghĩa

Đừng kiểm thử bằng giả định rằng `getDeclaredMethods()` luôn trả đúng một chuỗi cố định. Hãy kiểm thử **tính bất biến dưới phép hoán vị**: dù nhận danh sách các bản ghi theo thứ tự đầu vào nào, output chuẩn hóa phải giống nhau.

Ví dụ cách kiểm tra tổng quát:

~~~java
List<Method> input = new ArrayList<>(
        Arrays.asList(Sample.class.getDeclaredMethods()));

List<String> first = input.stream()
        .sorted(METHOD_ORDER)
        .map(StableReflectionReport::methodKeyForTest)
        .toList();

Collections.reverse(input);

List<String> reversed = input.stream()
        .sorted(METHOD_ORDER)
        .map(StableReflectionReport::methodKeyForTest)
        .toList();

if (!first.equals(reversed)) {
    throw new AssertionError("Metadata output depends on input order");
}
~~~

*Đây là minh họa kiểm thử tích hợp; cần các import `List`, `ArrayList`, `Arrays`, `Collections`, `Method`. `methodKeyForTest` là hàm do công cụ định nghĩa để xuất khóa chuẩn hóa; không phải phương thức sẵn có của Java. Với ví dụ hoàn chỉnh ở mục 4, có thể xây hàm này từ tên method, danh sách kiểu tham số, kiểu trả về và declaring class.*

Nên bổ sung trường hợp:

1. Hai overload cùng tên (`f(int)` và `f(String)`), để bảo đảm key không chỉ là tên.
2. Method bridge và method gốc, nếu công cụ xuất cả hai.
3. Hai field cùng tên khi dữ liệu gộp superclass và subclass.
4. Mảng parameter và lớp lồng nhau trong key.
5. Annotation element xuất từ một mảng method không có thứ tự được cam kết.
6. Hai nguồn metadata có tên giống nhau nhưng khác namespace/loader, nếu hệ thống của bạn hỗ trợ nhiều loader.

Phép kiểm tra đảo ngược đầu vào chứng minh một phần quan trọng: comparator đủ phân biệt các mục đang test. Nó **không thay thế** việc kiểm soát phiên bản Java, classpath, cấu trúc JSON, encoding hay chính sách lọc.

## 9. Các lỗi thường gặp

**“getDeclaredMethods() trả về thứ tự khai báo trong source.”** Không có bảo đảm đó. Đừng dùng chỉ số của mảng trả về làm số thứ tự tài liệu ổn định.

**“Chỉ sort theo method name là đủ.”** Không đủ với overload hoặc bridge. Khi key trùng, sort ổn định vẫn giữ thứ tự không ổn định của input.

**“Sort `getParameterTypes()` của từng method cho chắc.”** Sai. Thứ tự parameter **là một phần của chữ ký**; `f(int, String)` khác `f(String, int)`.

**“Dùng `Class.getSimpleName()` có thể định danh duy nhất.”** Không thể nếu có `a.User` và `b.User`. `Class.getName()` an toàn hơn trong một namespace nhưng cần thêm chính sách với nhiều loader.

**“Bỏ mọi synthetic method luôn đúng.”** Không đúng khi công cụ có trách nhiệm quan sát bytecode hoặc bridge cần thiết cho dispatch.

**“Sắp xếp metadata sẽ làm chương trình chạy đúng thứ tự method.”** Sort chỉ tác động tới trình bày/duyệt dữ liệu của công cụ. Nếu thứ tự thực thi có ngữ nghĩa, phải định nghĩa thứ tự đó riêng bằng cấu hình, annotation priority hoặc chính sách điều phối rõ ràng.

**“Cứ gọi `Method.toString()` rồi sort là canonical.”** Có thể dùng cho log đơn giản, nhưng khi xây giao thức ổn định nên dùng các getter và quy ước key có cấu trúc, tự kiểm soát định dạng.

**“Snapshot lệch sau khi sort nghĩa là comparator lỗi.”** Chưa chắc: classpath, compiler/JDK, annotation, thời gian, locale hay newline cũng có thể làm khác đầu ra.

## 10. Tự kiểm tra

1. Vì sao không in trực tiếp `Class.getDeclaredMethods()` để làm snapshot? **API không cam kết thứ tự.**
2. Vì sao khóa `Method.getName()` chưa đủ? **Overload có thể trùng tên; cần thêm kiểu tham số theo thứ tự, và thường thêm return/declaring type.**
3. Khi sắp xếp các method, có nên sort lại danh sách tham số bên trong từng method? **Không**, như vậy đổi ý nghĩa chữ ký.
4. Tại sao dùng `Method.isBridge()` / `isSynthetic()` phải phụ thuộc mục đích? **Vì một số công cụ muốn báo cáo API source-level, còn công cụ bytecode cần giữ metadata do compiler sinh.**
5. Hai `Class` cùng `getName()`, khác loader, có chắc là một kiểu không? **Không.**
6. Để tạo output ổn định, ngoài comparator cần kiểm soát gì? **Nguồn dữ liệu, chính sách lọc, format/generic/annotation, locale, encoding, newline và dữ liệu phụ thuộc môi trường.**
7. Nếu đầu vào đảo ngược mà output được sort vẫn khác, bạn nên kiểm tra gì đầu tiên? **Có các phần tử khác nhau nhưng comparator trả `0` hay không, và đã chuẩn hóa phần hiển thị chưa.**

## 11. Kết luận

Reflection giúp khám phá metadata ở runtime nhưng không hứa thứ tự trả về của nhiều API member. Để thiết kế công cụ xuất **ổn định và dễ kiểm chứng**, hãy xác định tập dữ liệu đúng, lọc theo mục đích, tạo key sort đủ phân biệt (đặc biệt với method overload), giữ nguyên thứ tự parameter mang ngữ nghĩa, rồi chuẩn hóa format và môi trường xuất. Một comparator tốt loại bỏ nhiễu do thứ tự liệt kê; tính tái lập đầy đủ còn cần một **hợp đồng canonical output** cho toàn pipeline.

### Tài liệu tham khảo

- [Java SE 21 — `Class`: các phương thức khám phá member](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 21 — `Constructor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Java SE 21 — `Comparator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html)
