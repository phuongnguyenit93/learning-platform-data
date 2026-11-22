# Kiểu tổng quát, mã sinh và phương thức cầu nối khi nền tảng có

Khi chọn điểm can thiệp bằng **pointcut** trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), mã nguồn thường không phải toàn bộ chương trình mà công cụ can thiệp thật sự nhìn thấy. Trình biên dịch hoặc runtime có thể tạo thêm phương thức, lớp đại diện, điểm chuyển tiếp và chữ ký đã biến đổi. Đặc biệt trong Java, **generics**, **type erasure**, **bridge methods** và **synthetic/generated members** có thể làm một quy tắc chọn phương thức hoạt động khác dự đoán.

Bài này tập trung vào một câu hỏi rất cụ thể của **pointcut cơ bản**: **khi xuất hiện kiểu tổng quát hoặc mã được tạo ra, những phương thức và chữ ký nào là đối tượng so khớp, và khi nào cần tính đến phương thức cầu nối?** Phần “khi nền tảng có” là điều kiện quan trọng: mỗi cơ chế AOP hỗ trợ một tập **join point** và quy tắc so khớp khác nhau; không được mặc định mọi phương thức trong bytecode đều được nhận diện thành execution join point hoặc đều được weave advice.

## 1. Điểm xuất phát: mã nguồn khác với biểu diễn sau biên dịch

Trong AOP:

- **Join point (điểm nối)** là điểm thực thi mà cơ chế AOP hỗ trợ can thiệp, chẳng hạn lời gọi hoặc phần thực thi phương thức.
- **Pointcut** là quy tắc chọn những join point được quan tâm.
- **Advice** là hành vi chạy tại những điểm được chọn.
- **Weaving** là quá trình kết hợp hành vi khía cạnh vào chương trình, có thể dựa trên mã nguồn, bytecode, lớp được nạp hoặc cơ chế chuyển tiếp lúc chạy.

Khi đọc một pointcut kiểu “chọn tất cả `handle(...)`”, ta thường nhìn vào phương thức Java do lập trình viên viết. Nhưng sau biên dịch, một lớp đôi khi có nhiều phương thức mang tên `handle` hơn số khai báo trong nguồn. Một trong số đó có thể là **bridge method** do compiler tạo để duy trì cơ chế gọi đa hình trên JVM.

Ba câu hỏi cần tách biệt:

1. **Mã nguồn mô tả gì?** Ví dụ `Handler<String>.handle(String)`.
2. **Bytecode/reflection thực tế có gì?** Ví dụ một phương thức `handle(String)` và một bridge `handle(Object)`.
3. **Mô hình join point của cơ chế AOP chọn được gì?** Nó có thể cố ý bỏ qua phương thức compiler-generated, chỉ quan sát một loại điểm nối, hoặc có các quy tắc ánh xạ riêng.

**Có hai phương thức xuất hiện trong Reflection không đồng nghĩa một lời gọi nghiệp vụ luôn có hai advice execution.** Đây là điểm quan trọng xuyên suốt bài.

## 2. Generics và type erasure tác động lên chữ ký ra sao?

Java generics giúp kiểm tra kiểu lúc biên dịch. Ví dụ:

~~~java
interface Handler<T> {
    T handle(T input);
}

final class TextHandler implements Handler<String> {
    @Override
    public String handle(String input) {
        return input.toUpperCase();
    }
}
~~~

Đây là các khai báo minh họa, chưa phải chương trình có `main`. Trong nguồn, khi `T=String`, người đọc có thể hình dung hợp đồng `handle(String):String`. Tuy nhiên, Java biên dịch generics bằng **type erasure**:

- Tham số kiểu chưa bị ràng buộc như `T` được xóa về `Object`.
- Tham số kiểu có bound được xóa về bound thích hợp (ví dụ `T extends Number` về `Number`).
- Compiler chèn các phép ép kiểu khi cần để giữ kiểm tra kiểu nguồn.
- Compiler **có thể tạo bridge method** để giữ hành vi override/đa hình sau khi chữ ký bytecode bị xóa kiểu.

Vì thế, chữ ký đã xóa kiểu của phương thức trong giao diện `Handler<T>` là dạng `Object handle(Object)`, trong khi phương thức chuyên biệt mà `TextHandler` viết là `String handle(String)`.

| Mức quan sát | Dạng ví dụ | Ý nghĩa |
| --- | --- | --- |
| Khai báo generic ở nguồn | `T handle(T)` | Hợp đồng tham số kiểu `T` |
| Khi gắn kiểu cụ thể | `String handle(String)` | Cách người dùng `Handler<String>` hiểu hợp đồng tại compile time |
| Chữ ký JVM sau erasure của hợp đồng | `Object handle(Object)` | Tên và descriptor mà JVM cần để liên kết lời gọi đã xóa kiểu |
| Phương thức chuyên biệt của lớp triển khai | `String handle(String)` | Phần thân nghiệp vụ do người viết |
| Phương thức cầu nối được compiler có thể tạo | `Object handle(Object)` | Bộ chuyển tiếp tương thích với chữ ký đã erasure |

**Không có lớp runtime riêng** `Handler<String>` và `Handler<Integer>` chỉ vì dùng hai đối số kiểu. Các thông tin generic có thể còn được giữ trong metadata chữ ký và được Reflection trả về bằng những API như `getGenericParameterTypes()`, nhưng điều đó không có nghĩa mọi pointcut hay mọi kiểu join point đều so khớp trực tiếp theo tham số kiểu nguồn.

### 2.1 “Generic type” có ít nhất ba lớp nghĩa

Khi một pointcut chọn theo kiểu, hãy phân biệt:

- **Declared generic signature:** ví dụ `Handler<T>`; có thể đọc được một phần qua metadata generic.
- **Erased JVM signature:** ví dụ tham số `Object`; đây là phần của descriptor sau biên dịch.
- **Runtime class của đối tượng/đối số:** ví dụ `TextHandler` và `String`; kiểm tra runtime target/args không đồng nghĩa đọc chữ ký generic.

Ví dụ một biến `List<String>` và một biến `List<Integer>` đều có thể trỏ tới đối tượng `ArrayList` cùng loại runtime class. Dựa vào `getClass()` không thể phân biệt hai tham số generic đó theo cách phân biệt hai runtime class thực sự khác nhau.

## 3. Phương thức cầu nối (bridge method) là gì?

**Bridge method** là phương thức do Java compiler sinh, thường được đánh dấu **bridge** và **synthetic**, để nối chênh lệch giữa ngữ nghĩa phương thức của Java ở mã nguồn và chữ ký/cơ chế dispatch ở JVM.

Ví dụ trước có thể được hình dung bằng **giả mã gần với bytecode**:

~~~java
// Chỉ là mô hình ý nghĩa; không được viết chung hai phương thức này
// như mã nguồn Java thường để thay compiler.
class TextHandler implements Handler<String> {
    public String handle(String input) {
        return input.toUpperCase();
    }

    // Bridge do compiler tạo cho descriptor đã xóa kiểu:
    public Object handle(Object input) {
        return handle((String) input);
    }
}
~~~

Phương thức cầu nối nhận `Object`, ép sang `String` rồi chuyển tiếp đến phần thân chuyên biệt. Nhờ đó, lời gọi được biên dịch thông qua hợp đồng generic đã xóa kiểu vẫn có thể đến đúng mã override.

**Vì sao cần?** Sau erasure, `Handler<T>.handle(T)` có descriptor dựa trên `Object`, nhưng phần triển khai `TextHandler.handle(String)` có descriptor dựa trên `String`. Nếu thiếu bước tương thích, việc gọi qua tham chiếu `Handler<String>` có thể không đi đúng phần thân chuyên biệt theo cơ chế dispatch của JVM.

### 3.1 Bridge không chỉ xuất hiện với generic

Bridge còn có thể được sinh để hỗ trợ **covariant return type** (override dùng kiểu trả về hẹp hơn) hoặc các khác biệt chữ ký cần giữ tính tương thích. Vì vậy không nên kết luận “`isBridge()==true` có nghĩa phương thức chắc chắn xuất phát từ một generic `T`” hoặc “mọi bridge đều có một tham số `Object`”.

### 3.2 Bridge và synthetic không phải cùng một khái niệm

Reflection của Java cung cấp:

- `Method.isBridge()`: cho biết phương thức được đánh dấu là bridge method.
- `Method.isSynthetic()`: cho biết phương thức là một phần tử synthetic, do công cụ/compiler tạo thay vì là khai báo nguồn thông thường theo cách mô tả của API.

Một bridge thường là synthetic, nhưng **không phải mọi phương thức synthetic đều là bridge**. Compiler cũng có thể tạo các thành phần phụ trợ khác. Khi muốn lọc bridge, hãy xét `isBridge()` cụ thể; khi muốn lọc mọi mã compiler-generated, `isSynthetic()` là một tín hiệu nhưng cũng cần hiểu giới hạn và chính sách của cơ chế đang dùng.

## 4. Vì sao bridge ảnh hưởng lựa chọn pointcut?

Một điểm quan trọng: **Reflection liệt kê phương thức trong class file**, còn **AOP lựa chọn join point theo mô hình riêng**. Hai danh sách không nhất thiết giống nhau.

Giả sử một lớp có hai descriptor thực tế:

~~~text
TextHandler.handle(String) -> String    (phương thức nghiệp vụ)
TextHandler.handle(Object) -> Object    (bridge synthetic)
~~~

Khi xây bộ chọn, cần phân biệt ít nhất bốn ý định:

1. **Chọn hành vi nghiệp vụ “handle” một lần trên mỗi lần gọi hợp lệ.** Có thể cần chuẩn hóa phương thức gốc/bridge tùy mô hình.
2. **Chọn mọi phương thức theo tên `handle`.** Bộ tìm kiếm Reflection không lọc bridge có thể trả cả hai, nhưng advice thực tế có được gắn cả hai hay không còn phụ thuộc AOP.
3. **Chọn theo tham số `String` hay `Object`.** Hai descriptor tồn tại khác nhau ở JVM; một mẫu quá hẹp có thể bỏ lỡ điểm được cơ chế thực sự expose.
4. **Chọn theo chữ ký nguồn generic.** Cần xem cơ chế AOP hiểu generic signature, erasure, quan hệ subtype và bridge như thế nào.

Nếu công cụ **instrument bytecode trên mọi entry method** mà không phân biệt bridge, một lời gọi qua bridge có thể đi qua cả bridge và phần thân chuyên biệt. Nếu advice được gắn ở cả hai entry, nó *có khả năng* được thực hiện hai lần cho một thao tác nghiệp vụ. Đây là **rủi ro của một số cách instrument**, không phải kết luận đúng cho mọi ngôn ngữ AOP.

Ngược lại, **một số hệ thống AOP chủ động loại bridge synthetic khỏi tập execution join point**. Chẳng hạn tài liệu về generic của một mô hình AOP có ngôn ngữ join point riêng ghi nhận rằng các bridge không có execution join point trong mô hình đó, dù các lời gọi có thể liên quan tới bridge theo ngữ nghĩa riêng. Do vậy, không nên khẳng định “cứ thấy bridge là sẽ có hai execution advice”.

### 4.1 Phân biệt điểm gọi và điểm thực thi

- **Call join point:** quan sát vị trí một lời gọi được phát sinh; chữ ký tĩnh tại call site và lớp nhận lời gọi có thể khác chữ ký của phương thức thực thi chuyên biệt.
- **Execution join point:** quan sát lúc một phần thân phương thức được thực hiện, theo cách mô hình AOP định nghĩa.

Ví dụ:

~~~text
Handler<String> h = new TextHandler()
                 |
                 v
      CALL theo hợp đồng đã erasure
                 |
                 v
        Bridge (nếu được dùng)
                 |
                 v
      TextHandler.handle(String)
                 |
                 v
       Phần thân nghiệp vụ
~~~

Sơ đồ mô tả một tuyến dispatch thường gặp sau biên dịch; nó **không khẳng định có join point AOP tại tất cả các mũi tên**. Có thể tồn tại bridge trong class file, nhưng mô hình AOP chỉ định nghĩa execution point cho phần thân chuyên biệt. Hoặc công cụ chặn ở ranh giới lời gọi qua proxy và không thấy chuyển tiếp nội bộ. Quy tắc thực tế phải kiểm tra theo phiên bản/cơ chế triển khai.

## 5. Ví dụ Java 17 chạy độc lập: nhìn thấy bridge bằng Reflection

Chương trình sau **không dùng một công cụ AOP cụ thể**. Nó dùng Reflection để thấy phương thức compiler-generated, từ đó minh họa vì sao một bộ phân tích pointcut cần phân biệt descriptor và cờ bridge. Ví dụ biên dịch với `javac` của JDK 17.

Lưu toàn bộ dưới tên `BridgePointcutDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class BridgePointcutDemo {
    interface Handler<T> {
        T handle(T value);
    }

    static final class TextHandler implements Handler<String> {
        @Override
        public String handle(String value) {
            System.out.println("BUSINESS " + value);
            return value.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Exception {
        Method contract = Handler.class.getMethod("handle", Object.class);
        System.out.println("CONTRACT "
                + contract.getParameterTypes()[0].getSimpleName()
                + " generic="
                + contract.getGenericParameterTypes()[0].getTypeName());

        List<Method> methods = Arrays.stream(
                    TextHandler.class.getDeclaredMethods())
                .filter(m -> m.getName().equals("handle"))
                .sorted(Comparator.comparing(Method::isBridge))
                .toList();

        for (Method method : methods) {
            System.out.println("METHOD "
                    + method.getParameterTypes()[0].getSimpleName()
                    + "->" + method.getReturnType().getSimpleName()
                    + " bridge=" + method.isBridge()
                    + " synthetic=" + method.isSynthetic());
        }

        long nameCandidates = methods.size();
        long businessCandidates =
                methods.stream().filter(m -> !m.isBridge()).count();
        System.out.println("CANDIDATES all=" + nameCandidates
                + " nonBridge=" + businessCandidates);

        TextHandler target = new TextHandler();
        Handler<String> throughContract = target;

        System.out.println("RESULT interface="
                + throughContract.handle("a"));
        System.out.println("RESULT direct=" + target.handle("b"));

        Method bridge = methods.stream()
                .filter(Method::isBridge)
                .findFirst().orElseThrow();
        System.out.println("RESULT reflectiveBridge="
                + bridge.invoke(target, "c"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BridgePointcutDemo.java
java BridgePointcutDemo
~~~

Đầu ra dự kiến với `javac` JDK 17:

~~~text
CONTRACT Object generic=T
METHOD String->String bridge=false synthetic=false
METHOD Object->Object bridge=true synthetic=true
CANDIDATES all=2 nonBridge=1
BUSINESS a
RESULT interface=A
BUSINESS b
RESULT direct=B
BUSINESS c
RESULT reflectiveBridge=C
~~~

### 5.1 Phân tích output

**`CONTRACT Object generic=T`**: `Handler<T>.handle(T)` đã có tham số erasure là `Object`, nhưng Reflection vẫn đọc được metadata generic `T` của khai báo.

**Hai dòng `METHOD`**: `TextHandler` có một phương thức nghiệp vụ với tham số/kiểu trả về `String`, và một bridge `Object -> Object` sinh để thích ứng hợp đồng đã erasure. `isBridge()` và `isSynthetic()` giúp phân biệt hai phương thức. Chương trình sắp xếp theo cờ bridge để đầu ra không phụ thuộc thứ tự `getDeclaredMethods()` trả về.

**`CANDIDATES all=2 nonBridge=1`**: nếu một bộ quét Reflection chỉ lọc tên `handle`, nó thấy hai candidate; nếu lọc `!isBridge()`, nó chỉ giữ phương thức chuyên biệt. Đó là **kết quả quét Reflection**, không phải số lần advice thực sự chạy.

**Ba lần `BUSINESS`**: mỗi lời gọi từ giao diện, lời gọi trực tiếp và lời gọi bridge bằng Reflection cuối cùng chỉ thực hiện phần thân chuyên biệt **một lần cho mỗi lời gọi trong ví dụ**. Một lời gọi qua bridge có thể bao gồm bước chuyển tiếp nội bộ nhưng không tự động in hai dòng `BUSINESS`.

**`RESULT reflectiveBridge=C`**: Reflection gọi bridge với đối số phù hợp `String`; bridge ép kiểu và chuyển tới thân `handle(String)`.

Các descriptor, cờ và việc sinh bridge trong output dựa trên **`javac` JDK 17** với đoạn nguồn đã cho. Một compiler, chế độ build hoặc môi trường instrument khác có thể sinh thêm/thay đổi mã tổng hợp; luôn đối chiếu class file hoặc Reflection thực tế trước khi đặt giả định cho pointcut.

### 5.2 Tại sao ví dụ không được gọi là một aspect hoàn chỉnh?

Chương trình chỉ liệt kê thành phần class file và gọi Java thông thường. Nó **không định nghĩa pointcut thực thi bởi một hệ thống AOP**, không weave advice và không chứng minh bộ AOP sẽ tác động vào cả bridge hay chỉ phương thức chuyên biệt. Mối liên hệ AOP nằm ở cách người thiết kế phải xử lý **phân loại candidate** và **quy tắc join point** trước khi áp dụng hành vi cắt ngang.

## 6. Mã sinh ngoài bridge: có những dạng nào?

Ngoài bridge, “mã sinh” có thể xuất hiện ở nhiều tầng. Không nên xem tất cả đều đồng nghĩa synthetic method.

| Nguồn tạo mã | Ví dụ | Vấn đề khi chọn pointcut |
| --- | --- | --- |
| **Compiler Java** | Bridge, một số phương thức phụ trợ, chi tiết triển khai lambda | Có thể xuất hiện tên/chữ ký không viết trong nguồn |
| **Proxy runtime** | Lớp đại diện triển khai interface và chuyển lời gọi qua handler | Kiểu runtime của proxy khác kiểu runtime của đối tượng nghiệp vụ |
| **Biến đổi bytecode** | Mã instrument được chèn vào lớp | Cơ chế AOP có thể nhìn thấy mã trước/sau biến đổi khác nhau |
| **Công cụ sinh mã khi build** | Lớp triển khai hoặc adapter được tạo từ mô hình nguồn | Mã sinh có thể là phương thức bình thường, **không nhất thiết synthetic** |
| **Lambda và method reference** | Cấu trúc thực thi do runtime/compiler triển khai | Danh tính lớp và thành phần phụ trợ có thể không ổn định để làm chính sách theo tên |

### 6.1 Proxy và đối tượng nghiệp vụ

Giả sử một proxy triển khai interface `Handler`, rồi chuyển lời gọi tới `TextHandler`. Lúc này có thể có hai đối tượng:

- **Proxy:** đối tượng mà bên gọi nắm giữ.
- **Target:** đối tượng `TextHandler` thật sự xử lý nghiệp vụ.

`proxy.getClass()` và `target.getClass()` không nhất thiết giống nhau. Pointcut theo runtime type phải xác định rõ nó kiểm tra **proxy**, **target**, **bên gọi** hay **đối số**. Một bộ chọn theo tên lớp proxy do runtime sinh có thể mong manh vì tên/lớp được tạo không phải hợp đồng nghiệp vụ.

Proxy qua giao diện cũng chỉ quan sát các lời gọi **thật sự đi qua proxy**. Lời gọi nội bộ trên đối tượng đích và lời gọi trực tiếp bỏ qua proxy có thể không chạy advice của proxy. Tập join point quan sát được khác với một hệ thống biến đổi bytecode có khả năng can thiệp các điểm sâu trong phần thân.

### 6.2 Synthetic không đồng nghĩa “cần bỏ qua”

Bridge synthetic có thể chỉ là adapter kỹ thuật. Nhưng trong một số chương trình, một phương thức được sinh có thể là điểm cần quan sát khi điều tra lỗi hoặc đo hạ tầng. Vì vậy không nên áp dụng quy tắc toàn cục “bỏ tất cả synthetic” cho mọi mục tiêu.

Ngược lại, các lớp do công cụ sinh ra có thể chứa phương thức **không được đánh dấu synthetic**. Nếu chỉ dựa vào `isSynthetic()`, bộ lọc không thể nhận diện tất cả mã sinh. Cần dựa vào mục đích pointcut, nguồn tạo mã và khả năng của mô hình join point.

## 7. Lựa chọn theo generic signature, erased signature và runtime args

Bốn cách chọn có thể tạo ra các tập điểm khác nhau:

| Ý định chọn | Thông tin cần xét | Nguy cơ nếu nhầm |
| --- | --- | --- |
| Chọn các phương thức có hợp đồng generic `Handler<T>` | Metadata generic và mô hình kiểu của công cụ | Erasure che mất tham số kiểu nguồn |
| Chọn phương thức có JVM parameter `Object` | Descriptor sau erasure | Có thể match bridge thay vì phần thân chuyên biệt |
| Chọn phần thân chuyên biệt `handle(String)` | Chữ ký thực của phương thức triển khai | Có thể bỏ sót các điểm gọi đi qua hợp đồng khi cơ chế dùng chữ ký khác |
| Chọn lần gọi có đối số runtime là `String` | Runtime argument binding/typing | `null` không có runtime class; dữ liệu runtime khác chữ ký khai báo |

Một số ngôn ngữ pointcut hỗ trợ diễn tả mẫu generic type và ràng buộc tham số phong phú; số khác chỉ làm việc với descriptor/Method của bytecode hoặc với chữ ký interface. Không được suy khả năng từ cú pháp Java generic ở mã nguồn.

### 7.1 Kiểu generic có bound

Với `T extends Number`, erasure của `T` có thể là `Number`, không phải `Object`. Một pointcut được viết dựa trên giả định “mọi generic đều bị xóa thành Object” sẽ sai cho generic có bound.

Cũng cần phân biệt **phương thức generic** `<T> T convert(T)` với **phương thức của lớp/giao diện generic**. Chữ ký generic có thể được lưu lại qua metadata; cách công cụ AOP đọc metadata đó phụ thuộc vào implementation.

### 7.2 Generic không luôn xác định được từ đối tượng runtime

Một đối số là `ArrayList<String>` tại vị trí gọi không mang riêng một runtime class có tên `ArrayList<String>`. Nếu pointcut muốn dựa trên kiểu phần tử `String`, có thể cần phân tích thông tin khai báo, kiểm tra dữ liệu một cách an toàn, hoặc chọn một thiết kế khác thay vì dựa vào `getClass()`.

Với **giá trị `null`**, không thể truy vấn runtime class; nhưng chữ ký phương thức vẫn có thông tin tham số được khai báo. Cách ngôn ngữ pointcut xử lý `null` trong biểu thức match kiểu runtime phải được kiểm tra riêng.

## 8. Method signature, overriding và bridge: những điểm tinh tế

### 8.1 Bridge do covariant return

Ví dụ một lớp con override phương thức trả về `Object` thành phương thức trả về `String`:

~~~java
class Parent {
    Object value() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String value() {
        return "child";
    }
}
~~~

Đây là **hai lớp minh họa**, không phải chương trình chạy độc lập. Ở mức Java, đây là override hợp lệ vì kiểu trả về `String` là kiểu con của `Object`. JVM phân biệt descriptor có return type; compiler có thể sinh bridge `Object value()` trong `Child` để giữ hành vi gọi đa hình cho mã dùng chữ ký của `Parent`.

Do đó bridge không chỉ gắn với trường hợp tham số kiểu `T` bị xóa thành `Object`. Nếu mục tiêu pointcut phụ thuộc vào kiểu trả về hoặc declaring class, phải xét cả trường hợp này.

### 8.2 Bridge không phải overload nghiệp vụ

Một lớp có thể có hai phương thức cùng tên vì **overload** do người viết chủ đích:

~~~java
void log(String message) { /* xử lý String */ }
void log(Object value)   { /* xử lý Object */ }
~~~

Đây là mảnh minh họa trong một lớp giả định. Cả hai đều là thành phần nghiệp vụ bình thường, không nên loại `log(Object)` chỉ vì nó có tham số `Object`. Phải dùng metadata `isBridge()` hoặc quy tắc nguồn được chứng minh, **không đoán bridge theo tên hoặc tham số**.

### 8.3 Annotation có thể nằm ở khai báo khác

Một annotation có thể nằm trên phương thức của interface, lớp cha, override chuyên biệt hoặc một thành phần generated. Không được tự giả định bridge mang mọi annotation của phương thức gốc, hoặc mọi cơ chế AOP tự đi tìm annotation ở interface/override giống nhau.

Trong Java, `@Inherited` áp dụng cho một phạm vi kế thừa annotation kiểu lớp; nó không tự tạo quy tắc kế thừa annotation phương thức qua mọi override. Pointcut dựa trên annotation phải xác định **đang quan sát Method nào** và **cơ chế tìm metadata nào**.

## 9. Nguy cơ thực tiễn: đếm trùng, bỏ sót và lựa chọn sai

### 9.1 Đếm trùng thao tác logic

Giả sử mục tiêu là “mỗi lần xử lý tin nhắn ghi đúng một sự kiện nghiệp vụ”. Nếu công cụ instrument cả bridge và phương thức chuyên biệt, một lời gọi qua bridge có thể phát sinh hai sự kiện. Từ đó thống kê request count, latency hoặc audit có thể tăng sai.

Cách xử lý có thể là chọn join point nghiệp vụ đã chuẩn hóa, loại bridge khi điều đó phù hợp, hoặc thiết kế nhận diện sự kiện sao cho không đếm trùng. **Nhưng chỉ lọc bridge khi đã chứng minh bridge thực sự là nguyên nhân**; một số mô hình AOP không tạo execution join point cho bridge, nên tự thêm bộ lọc có thể vô ích hoặc gây mất tín hiệu ở call join point.

### 9.2 Bỏ sót đường gọi

Ngược lại, chọn chỉ `handle(String)` có thể không khớp một loại **call join point** vốn biểu thị chữ ký `handle(Object)` do erasure, nếu bộ chọn làm việc ở lớp chữ ký đó. Cần xem nó phân tích nơi gọi, nơi thực thi, kiểu tĩnh hay runtime target; đừng sửa pointcut chỉ dựa trên một danh sách phương thức Reflection.

### 9.3 Nguy cơ khi dùng generated class làm điều kiện bảo mật

Nếu muốn kiểm tra quyền cho mọi thao tác theo interface `Handler`, việc chọn theo **tên lớp runtime được sinh** có thể bỏ sót đường gọi hoặc thay đổi khi cách tạo proxy đổi. Nên biểu diễn phạm vi theo hợp đồng nghiệp vụ/rành giới cần bảo vệ, xác minh tất cả đường gọi quan trọng, và thực hiện quyết định quyền trên danh tính đã được xác thực.

Một phép đếm phương thức hoặc log “advice đã chạy” ở một đường gọi không chứng minh toàn bộ đường truy cập dữ liệu đã được bảo vệ.

### 9.4 Lồng các advice và mã instrument tự sinh

Nếu một advice gọi hàm ghi log hoặc thống kê mà các hàm đó cũng khớp pointcut, mã bổ sung có thể **tự kích hoạt lại**. Mã được sinh bởi framework/runtime cũng có thể đi qua cùng phương thức nếu chọn quá rộng. Cần làm rõ ranh giới, điểm loại trừ và thứ tự can thiệp, đồng thời kiểm thử các đường phát sinh từ generated code.

## 10. Thiết kế pointcut chịu được biến đổi compiler/runtime

Một quy trình đánh giá phù hợp:

1. **Xác định mục tiêu:** muốn quan sát mỗi *lời gọi API*, mỗi *lần chạy thân phương thức*, hay mỗi *sự kiện nghiệp vụ*?
2. **Xác định loại join point:** call, execution, hoặc điểm chuyên biệt khác có được nền tảng hỗ trợ không?
3. **Xác định dữ liệu so khớp:** generic source metadata, JVM erased descriptor, lớp đích runtime, kiểu tham số runtime, annotation hay tên lớp generated?
4. **Xem lớp thực tế:** nếu làm việc ở JVM, kiểm tra `getDeclaredMethods()`, `isBridge()`, `isSynthetic()`, `getParameterTypes()`, `getGenericParameterTypes()` và bytecode khi cần.
5. **Đọc ngữ nghĩa công cụ:** nó có nhận bridge làm join point? Có bỏ qua synthetic? Có xử lý proxy, method override hoặc generic pattern đặc biệt không?
6. **Thử từng đường gọi:** qua interface, qua lớp cụ thể, qua proxy, trực tiếp, với giá trị null nếu hợp lệ, và với phương thức kế thừa/override.
7. **Kiểm tra kết quả advice:** mỗi sự kiện cần quan sát được ghi đúng số lần, vẫn giữ kết quả và ngoại lệ nghiệp vụ, không tạo overhead bất ngờ.

Nếu một nền tảng chỉ hỗ trợ proxy method calls, không nên đòi nó chọn các execution join point của mọi phương thức synthetic trong bytecode. Nếu một nền tảng hỗ trợ biến đổi bytecode, vẫn phải xác minh chính sách loại trừ mã sinh để tránh đếm trùng hoặc tác động ngoài phạm vi.

## 11. Ma trận kiểm thử pointcut

| Tình huống | Nguy cơ | Kết quả mong muốn cần xác minh |
| --- | --- | --- |
| `Handler<String>` gọi `TextHandler` qua interface | Descriptor sau erasure và bridge | Một sự kiện nghiệp vụ, số advice theo chính sách |
| Gọi `TextHandler.handle(String)` trực tiếp | Điểm gọi có chữ ký khác | Được chọn hoặc loại trừ đúng chủ đích |
| Reflection gọi bridge `handle(Object)` | Chuyển tiếp đến `handle(String)` | Không vô tình đếm hai lần nếu chỉ cần một |
| Override covariant return | Bridge có thể xuất hiện dù không có generic `T` | Không phân loại sai chỉ theo tên và tham số |
| Lớp được sinh nhưng không synthetic | Bộ lọc synthetic bỏ sót mã sinh | Phạm vi được quyết định theo chính sách, không chỉ một flag |
| Proxy chuyển tiếp vào đối tượng đích | Proxy class khác target class | Rõ runtime type nào được xét |
| Generic có bound `T extends Number` | Erasure không phải Object | Điểm match theo đúng descriptor/metadata |
| Annotation trên interface/override | Metadata ở nhiều nơi | Đúng khai báo và quy tắc lookup của công cụ |
| Lời gọi bỏ qua proxy | Advice proxy không chạy | Có rào chắn tại điểm bắt buộc nếu là chính sách an ninh |

## 12. Bài tập suy luận

**Bài tập 1.** Một ứng dụng có `Processor<T>.process(T)` và `TextProcessor implements Processor<String>`. Reflection thấy hai phương thức `process` trong lớp triển khai, một có `isBridge()==true`. Có được kết luận mọi lời gọi đều kích hoạt hai advice không?

**Đáp:** không. Reflection cho biết class file có hai phương thức; số join point và advice còn phụ thuộc mô hình AOP, loại pointcut và vị trí weaving. Có công cụ cố ý không tạo execution join point cho bridge.

**Bài tập 2.** Một pointcut theo chữ ký sau erasure mong tham số `Object`, nhưng code nghiệp vụ viết `process(String)`. Có thể xuất hiện phương thức `Object` ở đâu?

**Đáp:** từ hợp đồng generic đã erasure và có thể từ bridge do compiler sinh trên lớp triển khai. Không tự giả định tất cả các điểm đó đều là execution join point.

**Bài tập 3.** Nếu mục tiêu là đếm số thao tác nghiệp vụ xử lý tin nhắn, nên lấy `getDeclaredMethods().length` làm số nghiệp vụ không?

**Đáp:** không. Danh sách ấy có thể chứa bridge, synthetic và phương thức phụ trợ khác. Nên xác định một sự kiện nghiệp vụ và điểm quan sát ổn định theo hợp đồng.

**Bài tập 4.** Nếu `T extends Number`, erasure có phải luôn là Object?

**Đáp:** không; bound có thể tạo descriptor dựa trên `Number`.

**Bài tập 5.** Nếu một wrapper tạo ra lớp đại diện mới, `wrapper.getClass()` và `target.getClass()` có chắc giống nhau?

**Đáp:** không. Kiểu runtime phụ thuộc đối tượng nào được quan sát.

**Bài tập 6.** Nếu compiler không sinh bridge trong trường hợp đang xét, bài toán generic không còn ảnh hưởng pointcut?

**Đáp:** vẫn có thể ảnh hưởng. Erasure, kiểu tĩnh tại call join point, kiểu thực tế tại execution join point và metadata generic vẫn có thể tạo sự khác nhau về so khớp.

## Tài liệu tham khảo

- [Oracle Java Tutorials — Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html): cơ chế xóa kiểu và các hệ quả khi biên dịch.
- [Oracle Java Tutorials — Effects of Type Erasure and Bridge Methods](https://docs.oracle.com/javase/tutorial/java/generics/bridgeMethods.html): ví dụ compiler sinh bridge để giữ đa hình.
- [Java SE 17 — Method Reflection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `isBridge()`, `isSynthetic()`, `getGenericParameterTypes()`.
- [AspectJ Programming Guide — Join Points and Pointcuts](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): mô hình tham khảo về call/execution join point.
- [Generics in AspectJ 5 — Bridge Methods](https://eclipse.dev/aspectj/doc/released/adk15notebook/generics-inAspectJ5.html): ví dụ cụ thể cho việc bridge không tự động trở thành execution join point trong một mô hình AOP. Cần xem phiên bản tài liệu khớp nền tảng đang dùng.

**Ghi nhớ:** **generic trong mã nguồn → erasure ở bytecode → bridge/synthetic hoặc mã sinh khi cần → quy tắc join point/pointcut của nền tảng** là các tầng khác nhau. Một pointcut chính xác phải nêu rõ nó chọn **lời gọi, phần thực thi hay sự kiện nghiệp vụ nào**, theo **chữ ký và đối tượng nào**, và kiểm tra thực tế nền tảng có hỗ trợ những điểm đó trước khi áp dụng advice.
