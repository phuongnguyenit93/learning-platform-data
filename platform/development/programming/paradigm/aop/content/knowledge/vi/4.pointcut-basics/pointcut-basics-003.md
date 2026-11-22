# Khớp kiểu trả về, danh sách tham số và mức truy cập trong Pointcut

## 1. Mục tiêu của việc khớp chữ ký phương thức

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **pointcut** mô tả tập những *join point* (điểm thực thi có thể can thiệp) mà một chính sách cắt ngang muốn chọn. Với join point liên quan đến phương thức, một cách chọn thường gặp là dựa vào **chữ ký phương thức**: tên phương thức, kiểu khai báo, kiểu trả về, danh sách tham số và mức truy cập.

Ví dụ, ta muốn đo thời gian của những thao tác trả về `String`, nhận đúng một tham số `String`, và có mức truy cập `public`. Điều kiện này khác với yêu cầu “chọn mọi phương thức có chữ `find` trong tên”. Kiểu trả về và danh sách tham số giúp phân biệt các nhóm phương thức có cùng tên, còn mức truy cập giúp xác định điểm cần quan sát theo giao diện sử dụng của đối tượng.

Điểm quan trọng: **khớp chữ ký không đồng nghĩa với thực thi advice**. Một biểu thức có thể mô tả đúng phương thức cần chọn nhưng cơ chế AOP đang dùng chưa chắc can thiệp được phương thức đó. Vì vậy cần hiểu hai việc độc lập:

1. **Matching:** điều kiện pointcut có khớp với mô tả của một join point hay không?
2. **Interception/weaving:** công cụ có thật sự đưa lời gọi hoặc lần thực thi ấy qua advice hay không?

Bài này nói về khớp kiểu trả về, tham số, mức truy cập trong AOP tổng quát; mọi biểu thức minh họa sẽ được đánh dấu rõ là **mẫu khái niệm**, bởi các ngôn ngữ pointcut thực tế không hoàn toàn giống nhau.

## 2. Chữ ký phương thức gồm những thông tin nào?

Xét một lớp Java:

~~~java
class ProductCatalog {
    public String find(String sku) { return sku; }
    public String find(String sku, int limit) { return sku + limit; }
    protected Number total(int quantity, long price) {
        return quantity * price;
    }
    private void refreshCache() { }
}
~~~

Ví dụ trên là mã minh họa cấu trúc (không chứa `main` để chạy trực tiếp).

Từ chữ ký của phương thức `find(String sku)`, ta nhận diện:

- **Mức truy cập:** `public`.
- **Kiểu trả về khai báo:** `String`.
- **Tên phương thức:** `find`.
- **Danh sách tham số:** một phần tử kiểu `String`.
- **Lớp khai báo:** `ProductCatalog`.
- **Tên biến tham số:** `sku`, chỉ giúp người đọc hiểu ý nghĩa; tên biến không phải thành phần dùng để overload phương thức Java và thông thường không phải dữ liệu bắt buộc của signature matching.

Để diễn tả điều kiện một cách trực quan, có thể tưởng tượng khuôn mẫu:

~~~text
[visibility] [return-type] [declaring-type].[method-name]([parameter-pattern])
~~~

Đây là **ký pháp giảng giải**, không phải cú pháp bảo đảm hoạt động trong mọi engine AOP. Tùy công nghệ, pointcut có thể dùng mẫu tên, toán tử điều kiện, annotation, biểu thức lọc thời điểm thực thi, hay một API lập trình để thực hiện cùng ý định chọn điểm.

Chữ ký phương thức cũng không cho ta biết toàn bộ hoạt động tại runtime. Một phương thức có thể gọi nhiều phương thức khác, ném ngoại lệ, hoặc được triển khai lại trong lớp con. Tránh nhầm “chữ ký mô tả điểm” với “nghiệp vụ bên trong điểm”.

## 3. Khớp kiểu trả về: chính xác hay theo quan hệ kiểu?

**Kiểu trả về khai báo** là kiểu đứng trước tên phương thức. Ví dụ:

~~~java
public String label() { return "ok"; }
public Object data() { return "ok"; }
public int quantity() { return 3; }
public Integer boxedQuantity() { return 3; }
public void reset() { }
~~~

Các phương thức trên đều có thể có cùng loại kết quả runtime trong một số lần gọi, nhưng kiểu trả về *khai báo* của chúng khác nhau. `label()` khai báo `String`, còn `data()` khai báo `Object` dù nó trả về đối tượng `String` ở ví dụ. Một pointcut khớp kiểu khai báo `String` không nên tự suy ra `data()` sẽ khớp chỉ vì giá trị trả về hiện tại là chuỗi.

### 3.1. Khớp kiểu chính xác

Một điều kiện khớp **chính xác** `String` chọn phương thức có kiểu trả về khai báo tương ứng, nếu engine áp dụng quy tắc này. Trong Java Reflection, ta có thể kiểm tra:

~~~java
method.getReturnType() == String.class
~~~

Với `void`, dùng `void.class`; với kiểu nguyên thủy, `int.class` khác `Integer.class`. Mẫu `Number` khác `int`, và `Integer` không tự đồng nhất với `int` khi so khớp chữ ký bằng `Class<?>`.

### 3.2. Khớp theo phân cấp kiểu

Một cơ chế khác có thể cho phép điều kiện theo subtype hoặc tính gán được. Ví dụ, `Number.class.isAssignableFrom(Integer.class)` là `true`; nhưng `Number.class.isAssignableFrom(int.class)` là `false`. Nếu công cụ hỗ trợ điều kiện kiểu rộng hơn, hãy kiểm tra *hướng quan hệ kiểu* và khả năng khớp khai báo của công cụ. Không tự chuyển quy tắc reflection thành cú pháp pointcut của mọi engine.

Điều kiện `Object` cũng không đồng nghĩa với “mọi kiểu trả về” dưới quy tắc gán được thông thường, bởi primitive và `void` cần xem xét riêng.

### 3.3. Kiểu khai báo so với giá trị runtime

`Object load()` có thể trả `new String("x")` trong lần gọi hiện tại và một kiểu khác lần sau. **Pointcut chọn theo chữ ký** thường quyết định dựa trên mô tả tĩnh của phương thức, không dựa vào loại đối tượng vừa trả về. Nếu chính sách muốn quyết định theo kết quả thực tế, đó có thể là điều kiện xử lý trong **advice sau khi thực thi**, không còn là cùng một điều kiện chỉ dựa vào chữ ký.

### 3.4. Covariant return và bridge method

Java cho phép phương thức override trả về kiểu con phù hợp:

~~~java
class Parent {
    Number value() { return 1; }
}
class Child extends Parent {
    @Override
    Integer value() { return 2; }
}
~~~

Khi xem chữ ký khai báo ở `Parent` và `Child`, kiểu trả về khác nhau. Trình biên dịch còn có thể sinh **bridge method** phục vụ đa hình hoặc generic erasure. Một công cụ phân tích bytecode có thể nhìn thấy phương thức tổng hợp mà người viết không chủ ý khai báo trực tiếp. Khi các pointcut chọn theo signature, cần xác minh engine xử lý bridge/synthetic method thế nào, và liệu một thao tác có bị ghi nhận hai lần không. Java Reflection cung cấp `Method.isBridge()` và `Method.isSynthetic()` để phân tích.

## 4. Khớp danh sách tham số: số lượng, thứ tự và kiểu

Tham số của một phương thức được phân biệt bởi **số lượng** và **kiểu theo thứ tự**. Ba phương thức sau là ba overload khác nhau:

~~~java
void send(String value) { }
void send(String value, int attempts) { }
void send(int attempts, String value) { }
~~~

Nếu pointcut yêu cầu đúng `(String, int)`, nó không khớp `(String)` và cũng không khớp `(int, String)`. Đây là một trong những lỗi chọn nhầm phương thức phổ biến khi tên phương thức trùng nhau.

Một số dạng điều kiện thường gặp:

| Ý định | Cách hiểu |
| --- | --- |
| Không tham số | Chọn phương thức có danh sách tham số rỗng `()` |
| Chính xác một `String` | Danh sách có một phần tử kiểu `String` |
| Chính xác `(String, int)` | Hai tham số theo đúng thứ tự và kiểu |
| Tham số đầu là `String`, còn lại tùy ý | Cần cơ chế biểu diễn phần đuôi có độ dài linh hoạt |
| Có bất kỳ danh sách tham số nào | Điều kiện không giới hạn số lượng/kiểu |
| Tham số thuộc phân cấp `Number` | Phải làm rõ khớp chính xác hay subtype |

Các ký hiệu wildcard như `*` hoặc `..` thường xuất hiện trong một số ngôn ngữ pointcut, nhưng **ý nghĩa và vị trí hợp lệ phụ thuộc công cụ**. Đừng mặc định `(..)` luôn có cùng nghĩa ở mọi công nghệ; ký pháp `String, ..` hay `*, String` cũng có thể được hỗ trợ khác nhau.

### 4.1. Primitive khác wrapper

`int` khác `Integer`; `long` khác `Long`. Java cho phép boxing/unboxing tại nhiều vị trí lời gọi, nhưng **kiểu tham số được khai báo** vẫn khác nhau. Chọn chữ ký `process(Integer)` không tự nhiên khớp mọi `process(int)` chỉ vì lời gọi Java có thể tự boxing.

### 4.2. Mảng và varargs

Khai báo `accept(String... values)` sử dụng varargs ở phía lời gọi, nhưng chữ ký phản chiếu của nó có **một tham số kiểu `String[]`**. Có thể kiểm tra `Method.isVarArgs()` nếu muốn phân biệt ý định varargs; dùng `getParameterTypes()` sẽ thấy kiểu mảng.

Tương tự, `accept(String[])` và `accept(String...)` có cùng biểu diễn tham số ở mức chữ ký JVM, nên không thể overload hai khai báo ấy trong cùng một lớp chỉ bằng dấu ba chấm.

### 4.3. Generic và type erasure

Với `List<String>` và `List<Integer>`, thông tin generic có thể còn trong metadata nhưng Java **erasure** khiến kiểu tham số runtime đều là `List` ở nhiều phép đối chiếu. Reflection `getParameterTypes()` trả về lớp thô; `getGenericParameterTypes()` cho thông tin generic nếu metadata được lưu. Một engine AOP có thể khớp signature sau erasure hoặc dùng metadata generic theo quy tắc riêng. Không khẳng định mọi pointcut phân biệt được `List<String>` với `List<Integer>`.

### 4.4. Tên tham số không phải khóa chính

`pay(int amount)` và `pay(int value)` có cùng chữ ký overload theo kiểu tham số; đổi tên biến không tạo overload mới. Trong thực tế, metadata tên tham số có thể không được bảo toàn như source nếu cách biên dịch khác nhau, nên chọn pointcut theo kiểu và thứ tự tham số đáng tin hơn chọn theo tên biến.

### 4.5. Signature pattern khác binding giá trị thực tế

Có sự khác nhau giữa yêu cầu **“chỉ các phương thức có tham số kiểu `String`”** và **“chỉ những lần gọi mà giá trị `String` thực tế thỏa điều kiện nào đó”**. Trường hợp thứ nhất dựa trên chữ ký; trường hợp thứ hai cần ngữ cảnh runtime hoặc điều kiện trong advice. Kết hợp cả hai phải xác định chính xác thời điểm chọn, đặc biệt với `null`, subtype và overload.

## 5. Khớp mức truy cập: public, protected, package-private, private

Java có bốn mức truy cập cần hiểu khi chọn join point:

| Mức truy cập | Khai báo | Ý nghĩa chính trong Java | Điều cần nhớ khi áp dụng pointcut |
| --- | --- | --- | --- |
| **public** | `public` | Truy cập rộng rãi theo các ràng buộc module/type | Thường xuất hiện ở hợp đồng API nhưng chưa chắc mọi lời gọi được proxy chặn |
| **protected** | `protected` | Truy cập trong package và ở subclass theo quy tắc Java | Có thể yêu cầu can thiệp trong class/subclass; phụ thuộc cơ chế |
| **package-private** | Không ghi modifier truy cập | Truy cập trong cùng package | Không phải từ khóa `package-private` trong source |
| **private** | `private` | Chỉ truy cập theo quy tắc private của Java | Proxy dựa trên override thường không thể override phương thức private |

**Mức truy cập** là một đặc điểm của khai báo Java; **khả năng intercept** còn phụ thuộc cơ chế AOP. Một engine chỉ quan sát lời gọi đi qua interface công khai không đồng nghĩa với việc nó thực thi được advice tại bất kỳ method `private` nào trong đối tượng gốc. Ngược lại, một hệ thống weaving trong bytecode có thể hỗ trợ những join point không thể quan sát bằng proxy, nếu mô hình join point và vùng weaving cho phép.

### 5.1. Không nhầm với modifier khác

`static`, `final`, `abstract` và `synchronized` không phải là bốn mức truy cập. Ví dụ, `public final boolean ready()` vẫn là **public**. Tuy nhiên `final` có thể hạn chế cơ chế proxy cần override phương thức; `static` không là lời gọi instance thông thường. Các chi tiết này quan trọng để đánh giá khả năng can thiệp, nhưng không được dùng thay cho phép lọc theo `public/protected/package-private/private`.

### 5.2. Lớp khai báo và thành viên thực sự được quan sát

Một phương thức public trong một lớp không public, một phương thức được kế thừa, hoặc một method được override có thể được biểu diễn khác nhau ở caller, interface và implementation. Khi áp dụng pointcut, phải xác định engine dùng **chữ ký được nhìn tại vị trí gọi**, **chữ ký implementation**, hay **join point tại lần thực thi**. Các kết quả không phải lúc nào cũng tương đồng.

Với Java Reflection:

- `Class.getMethods()` trả các phương thức public có thể truy cập theo API Reflection, gồm các thành viên kế thừa.
- `Class.getDeclaredMethods()` trả phương thức được khai báo trực tiếp trong lớp, ở mọi mức truy cập, nhưng không trả các phương thức chỉ được kế thừa.
- `Method.getModifiers()` kết hợp với `Modifier.isPublic()`, `isProtected()` và `isPrivate()` giúp kiểm tra mức truy cập. Nếu cả ba đều false, đó là package-private trong mô hình Java thông thường.

Dù Reflection nhận diện được một phương thức private, điều đó **không chứng minh** công cụ AOP có thể đặt advice vào mọi lần thực thi private.

## 6. Ví dụ Java 17+: kiểm tra pointcut theo cả ba trục

Ví dụ dưới đây sử dụng **Reflection để mô phỏng bước lựa chọn chữ ký**: mỗi hàm predicate đại diện cho một pointcut cụ thể; chương trình liệt kê phương thức khớp. Đây là ví dụ Java 17+ chạy độc lập, **không phải hệ thống weaving, cũng không chạy advice**. Việc không chạy advice là có chủ đích: trước hết ta cần kiểm chứng chính xác **bộ chọn** để tránh nhầm lẫn nó với cơ chế can thiệp.

Tạo tệp `SignaturePointcutDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class SignaturePointcutDemo {
    static class Catalog {
        public String find(String code) { return code; }
        public String find(String code, int limit) { return code + limit; }
        protected Number total(int quantity, long price) {
            return quantity * price;
        }
        private void refresh() { }
        static int version() { return 1; }
        public final boolean ready() { return true; }
    }

    static boolean types(Method method, Class<?> result, Class<?>... parameters) {
        return method.getReturnType() == result
                && Arrays.equals(method.getParameterTypes(), parameters);
    }

    static String signature(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));
        return method.getName() + "(" + parameters + ")";
    }

    static void report(String rule, Predicate<Method> pointcut) {
        String matches = Arrays.stream(Catalog.class.getDeclaredMethods())
                .filter(pointcut)
                .map(SignaturePointcutDemo::signature)
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println(rule + ": "
                + (matches.isEmpty() ? "(none)" : matches));
    }

    public static void main(String[] args) {
        report("public String(String)", method ->
                Modifier.isPublic(method.getModifiers())
                        && types(method, String.class, String.class));
        report("public String(String,int)", method ->
                Modifier.isPublic(method.getModifiers())
                        && types(method, String.class, String.class, int.class));
        report("protected Number(int,long)", method ->
                Modifier.isProtected(method.getModifiers())
                        && types(method, Number.class, int.class, long.class));
        report("private void()", method ->
                Modifier.isPrivate(method.getModifiers())
                        && types(method, void.class));
        report("public int()", method ->
                Modifier.isPublic(method.getModifiers())
                        && types(method, int.class));
        report("package-private int()", method ->
                !Modifier.isPublic(method.getModifiers())
                        && !Modifier.isProtected(method.getModifiers())
                        && !Modifier.isPrivate(method.getModifiers())
                        && types(method, int.class));
        report("public boolean()", method ->
                Modifier.isPublic(method.getModifiers())
                        && types(method, boolean.class));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 SignaturePointcutDemo.java
java SignaturePointcutDemo
~~~

Đầu ra đã kiểm chứng:

~~~text
public String(String): find(String)
public String(String,int): find(String, int)
protected Number(int,long): total(int, long)
private void(): refresh()
public int(): (none)
package-private int(): version()
public boolean(): ready()
~~~

**Giải thích kết quả:**

1. `public String(String)` chỉ khớp `find(String)`; overload `find(String,int)` không có đúng một tham số.
2. `public String(String,int)` chọn overload hai tham số theo đúng thứ tự.
3. `protected Number(int,long)` chọn `total(int,long)`, không cần biết số thực tế được trả về.
4. `private void()` chọn `refresh()` dù phương thức private không thể được proxy chặn theo mọi cơ chế. **Matching thành công không chứng minh advice sẽ chạy.**
5. `public int()` không chọn `version()` vì `version()` là package-private.
6. `package-private int()` chọn `version()`; modifier `static` không làm nó trở thành public.
7. `public boolean()` chọn `ready()` dù phương thức có thêm modifier `final`.

`Arrays.equals(method.getParameterTypes(), parameters)` so kiểu khai báo và thứ tự tham số chính xác. `getDeclaredMethods()` được dùng để nhìn cả method private/protected của chính `Catalog`. Hàm `sorted()` giúp thứ tự in kết quả ổn định, tránh phụ thuộc thứ tự mà Reflection trả ra.

Nếu muốn dùng kết quả chọn của một predicate để làm pointcut trong cơ chế AOP thực, cần thêm bước gắn với **join point mà công cụ hỗ trợ** và kiểm thử advice ở đúng đường gọi. Chương trình này chỉ xác minh cú pháp Java và **logic lựa chọn chữ ký**.

## 7. Kết hợp ba trục trong một pointcut thực tế

Một pointcut có thể ghép nhiều điều kiện bằng logic AND:

~~~text
P(method) =
    method.access == PUBLIC
    AND method.declaredReturnType == String
    AND method.name == "find"
    AND method.parameterTypes == [String, int]
~~~

Đây là **mô tả thuật toán chọn**, không phải một cú pháp dùng được ngay trong engine bất kỳ. Điều kiện ấy sẽ chọn `public String find(String,int)`, đồng thời loại bỏ `find(String)` vì số tham số khác, `protected Number total(int,long)` vì tên, kiểu trả về và mức truy cập khác.

Muốn chọn nhiều chữ ký có thể dùng logic OR giữa các điều kiện đã định nghĩa; muốn loại trừ utility method có thể dùng NOT ở nơi công cụ hỗ trợ. Lưu ý: pointcut quá rộng (ví dụ mọi phương thức public trả `String`) có thể bao cả getter và phương thức tiện ích không liên quan; pointcut quá hẹp (chỉ một overload) có thể bỏ sót những lời gọi mà nghiệp vụ cần audit.

Một cách thực hành là lập **bảng phải khớp/không được khớp** trước khi hiện thực:

| Phương thức | Khớp `public String find(String,int)`? | Vì sao |
| --- | --- | --- |
| `public String find(String,int)` | Có | Tất cả điều kiện trùng |
| `public String find(String)` | Không | Thiếu tham số `int` |
| `protected String find(String,int)` | Không | Mức truy cập khác |
| `public Object find(String,int)` | Không với khớp chính xác | Kiểu trả về khai báo khác |
| `public String find(int,String)` | Không | Thứ tự tham số khác |
| `public String lookup(String,int)` | Không | Tên khác |

Bảng này là ví dụ cho bộ chọn **khớp chính xác tất cả thành phần**, không phải kết luận về một cú pháp pointcut cụ thể. Khi engine cho phép mẫu wildcard hoặc phép chọn theo subtype, các dòng có thể có kết quả khác theo chính sách đó.

## 8. Ranh giới của call và execution khi khớp chữ ký

AOP có thể mô tả hai điểm can thiệp khác nhau:

- **Method call join point:** nơi mã gọi một phương thức. Nó gắn với phía caller và thông tin về lời gọi.
- **Method execution join point:** nơi thân phương thức thực sự được thực thi. Nó gắn với phía callee/implementation.

Nếu một biến khai báo theo interface nhưng đối tượng thật là implementation, chữ ký người gọi thấy có thể khác với chữ ký được phản chiếu trên method implementation, đặc biệt khi có override và kiểu trả về covariant. Ngoài ra, dynamic dispatch có thể chọn một thân phương thức khác với điều người đọc đoán từ tên biến.

Ví dụ minh họa:

~~~java
interface Reader {
    Object read();
}
class JsonReader implements Reader {
    @Override
    public String read() { return "json"; }
}
~~~

Về khai báo, `Reader.read()` trả `Object`, còn `JsonReader.read()` trả `String`. Nếu công cụ phân biệt **call** với **execution**, dùng kiểu trả về trong bộ lọc phải hiểu nó gắn với join point nào, tránh tưởng rằng chỉ có một chữ ký duy nhất tồn tại ở mọi tầng.

Đây cũng là lý do không nên bê nguyên một bộ predicate Reflection và mặc định nó tương đương với cả hai dạng pointcut. Reflection xem một `Method` cụ thể, trong khi engine AOP có thể định nghĩa quy tắc resolution theo điểm gọi, điểm thực thi, declaring type hoặc kiểu runtime.

## 9. Các giới hạn can thiệp theo công cụ

### 9.1. Chọn được không có nghĩa là chặn được

Một chương trình Reflection có thể tìm `private void refresh()`. Một **proxy qua interface** lại chỉ can thiệp được lời gọi qua interface của nó. Nếu `refresh()` chỉ được gọi bên trong target thì proxy không nhìn thấy đường đó. Phương thức được đánh dấu `final` cũng có thể gây giới hạn với một proxy cần override, dù nó là `public`.

Một cơ chế **bytecode weaving** có thể can thiệp sâu hơn trong thân phương thức nếu nó thực sự hỗ trợ loại join point tương ứng và lớp chứa method nằm trong vùng được weaving. Không thể suy ra tính năng weaving từ việc một công cụ tự nhận là “AOP”.

### 9.2. Modifier và phạm vi truy cập khác biệt

Mức `private`, package-private, `protected` và `public` tuân theo quy tắc truy cập Java, nhưng khả năng phân giải chữ ký, gọi reflection, class visibility, module boundary, classloader và cách công cụ proxy/weaving hoạt động có thể giới hạn thêm. Trên JDK có module mạnh, “biết `Method` tồn tại” không đồng nghĩa “luôn được phép truy cập/instrument ở runtime”.

### 9.3. Overload, override, bridge, synthetic

Pointcut chỉ dùng tên dễ chọn nhầm overload. Với override, engine có thể xem xét chữ ký khai báo và kiểu implementation. Với bridge/synthetic methods, hãy kiểm tra luật lọc của công cụ trước khi tính metrics hay audit để tránh ghi trùng. Đây là chi tiết nâng cao, nhưng có thể gây lỗi nếu tác động cắt ngang đòi hỏi chính xác số lần gọi.

### 9.4. Generic và varargs không giữ nguyên hình thức source

Signature ở mức bytecode có thể khác cách người đọc hiểu từ mã nguồn có generic và varargs. Điều kiện pointcut cần dựa trên đúng loại metadata engine hỗ trợ. Nếu engine xử lý kiểu sau erasure, cố chọn `List<String>` chính xác có thể không có nghĩa như mong đợi.

### 9.5. Phân biệt lựa chọn tĩnh và quyết định động

Bộ lọc `return type` và `parameter types` dựa trên khai báo thường có thể kiểm tra trước khi lời gọi chạy. Kiểm tra nội dung runtime, như `quantity > 0`, cần dữ liệu đối số trong lúc thực thi, hoặc lời khuyên xử lý trong advice. Không đánh đồng **matching một phương thức có tham số `int`** với **lọc những lời gọi có giá trị `int` dương**.

## 10. Thiết kế và kiểm thử pointcut có thể bảo trì

Một quy trình có thể áp dụng cho việc lựa chọn theo ba trục:

1. **Nêu đúng hành vi cắt ngang:** muốn audit, tracing, metrics hay ràng buộc truy cập nào? Nếu chính sách chỉ áp dụng cho giao diện API, mô tả ranh giới ấy trước.
2. **Liệt kê các chữ ký mẫu:** bao gồm overload cùng tên, kiểu trả về khác, tham số đảo thứ tự và mức truy cập khác. Đây là bộ mẫu xác minh đầu tiên.
3. **Chọn quy tắc so kiểu:** khớp chính xác, subtype hay wildcard? Primitive, wrapper, mảng, generic có ý nghĩa thế nào?
4. **Chọn loại join point:** call hay execution, và phương thức thuộc interface hay implementation? Phạm vi can thiệp có hỗ trợ private/final/static hay không?
5. **Kiểm tra matching độc lập:** như chương trình Reflection ở trên để rõ logic mong muốn; khi chuyển sang engine AOP, thêm bài kiểm tra thật trên engine.
6. **Chạy qua ranh giới thực:** xác minh số lần advice chạy khi lời gọi đúng/không đúng điều kiện; kiểm tra trường hợp target được gọi trực tiếp, self-invocation và overload khác.
7. **Kiểm tra kết quả và tác dụng phụ:** advice chỉ quan sát không nên vô tình thay kết quả, ngoại lệ, số lần chạy nghiệp vụ hoặc dữ liệu nhạy cảm.

Bảng kiểm thử tối thiểu cho một pointcut chọn `public String find(String,int)`:

| Ca thử | Kỳ vọng matching | Kỳ vọng về advice khi engine hỗ trợ điểm tương ứng |
| --- | --- | --- |
| Gọi đúng overload với `("X", 2)` | Match | Chạy một lần theo chính sách |
| Gọi `find("X")` | Không match | Không chạy |
| Gọi phương thức cùng tên khác quyền truy cập | Không match | Không chạy |
| Gọi method cùng tên nhưng kiểu trả về khác | Không match với exact type | Không chạy |
| Gọi trực tiếp target bỏ qua proxy | Chữ ký vẫn match về mặt lý thuyết | Có thể không chạy vì bỏ qua ranh giới |
| Gọi nội bộ `this.find(...)` | Chữ ký có thể match | Tùy proxy/weaving, phải kiểm chứng |
| Có bridge method hoặc nhiều advice | Phụ thuộc bộ chọn và engine | Không được phát sinh audit trùng ngoài ý muốn |

## 11. Lỗi thường gặp khi khớp chữ ký

- **Nhầm `Object` với mọi kiểu trả về:** primitive và `void` cần xử lý riêng; phân biệt exact match với quan hệ assignability.
- **Dựa vào kiểu của giá trị trả về runtime:** chữ ký mô tả kiểu *khai báo*, không phải giá trị ngẫu nhiên trong một lần chạy.
- **Bỏ qua thứ tự tham số:** `(String,int)` khác `(int,String)`.
- **Lẫn primitive với wrapper:** `int` và `Integer` là hai kiểu khai báo khác nhau.
- **Coi varargs là nhiều tham số tùy ý:** `String...` tương ứng với một tham số mảng `String[]` ở JVM.
- **Quên generic erasure và bridge methods:** có thể chọn sai hoặc ghi trùng trong các mô hình áp dụng theo bytecode.
- **Coi package-private là một modifier viết trong source:** nó xuất hiện khi không ghi `public/protected/private`.
- **Cho rằng public luôn chặn được và private luôn giống nhau giữa mọi engine:** khả năng can thiệp phụ thuộc proxy/weaving và điểm thực thi.
- **Áp dụng mẫu wildcard mà chưa xác minh cú pháp:** ký hiệu và ý nghĩa phải dựa trên tài liệu của công cụ sử dụng.
- **Chỉ kiểm thử predicate, bỏ kiểm thử advice thực tế:** matching đúng chưa đủ chứng minh pointcut chạy trên đường gọi thực.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `public String get(String)` và `public String get(String,int)` có cùng tên. Pointcut yêu cầu chính xác một tham số `String` chọn được phương thức nào?  
**Đáp án:** Chỉ `get(String)`; số lượng tham số của overload còn lại khác.

**Câu 2.** `public Object get()` luôn trả về đối tượng `String` trong chương trình đang chạy. Quy tắc khớp kiểu trả về khai báo chính xác `String` có chọn `get()` không?  
**Đáp án:** Không; kiểu trả về khai báo là `Object`.

**Câu 3.** `private void refresh()` có thể được Reflection tìm thấy bằng `getDeclaredMethods()`. Có đủ kết luận mọi engine proxy có thể chạy advice ở phương thức ấy không?  
**Đáp án:** Không. Reflection dùng để xem metadata; can thiệp phụ thuộc join point model và kỹ thuật proxy/weaving.

**Câu 4.** Khác biệt chính giữa `String... values` và `String[] values` khi đối chiếu signature JVM là gì?  
**Đáp án:** Cả hai đều có một tham số kiểu `String[]`; có thể dùng thông tin varargs riêng để nhận biết cách khai báo/hành vi gọi.

**Câu 5.** Muốn biết advice chạy đúng phải kiểm tra điều gì ngoài signature?  
**Đáp án:** Loại join point call/execution, phạm vi proxy/weaving, đường gọi thực, thứ tự advice và số lần kích hoạt.

## 13. Ghi nhớ

Pointcut khớp chữ ký là cách chọn phương thức theo **kiểu trả về, danh sách tham số và mức truy cập**, thường kết hợp thêm tên và kiểu khai báo. Khi viết quy tắc, phải phân biệt **khớp chính xác với khớp theo quan hệ kiểu**, **kiểu khai báo với dữ liệu runtime**, **primitive với wrapper**, **overload với override**, và **signature matching với interception thực tế**. Thiết kế một bảng những phương thức phải/không được chọn, rồi kiểm thử trên đúng cơ chế AOP được sử dụng, sẽ giúp advice áp dụng đúng phạm vi mà vẫn giữ mã nghiệp vụ rõ ràng.