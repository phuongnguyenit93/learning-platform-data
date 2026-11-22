# Nhận diện phương thức bridge, synthetic và varargs

## Khái niệm: reflection nhìn đầu ra đã biên dịch

Khi dùng reflection để liệt kê phương thức, danh sách nhận được không nhất thiết trùng một-một với các phương thức mà người viết nhìn thấy trong mã nguồn.

Trình biên dịch có thể tạo thêm phương thức để giữ đúng hành vi ngôn ngữ sau khi dịch sang class file. Đồng thời, một số thuộc tính khai báo như varargs cần được phản ánh bằng cờ riêng dù kiểu tham số lúc chạy là mảng.

Ba API cần phân biệt:

| API trên Method | Câu hỏi |
| --- | --- |
| `isBridge()` | Phương thức có được đánh dấu là phương thức cầu nối không? |
| `isSynthetic()` | Phương thức có được đánh dấu synthetic không? |
| `isVarArgs()` | Phương thức có được khai báo nhận số lượng đối số biến đổi không? |

Ba câu hỏi độc lập về ý nghĩa. Không dùng một cờ để suy ra tất cả các cờ còn lại.

Các cơ chế này vẫn áp dụng trong Java hiện đại. Ví dụ trong bài được thiết kế cho JDK 17 trở lên và không cần thư viện ngoài.

## Vì sao cần nhận diện khi quét phương thức?

Một công cụ dựa trên reflection có thể muốn:

- Tạo tài liệu API từ các khai báo mà người viết quan tâm.
- Tìm phương thức xử lý theo quy ước.
- Đọc chữ ký generic và annotation.
- Xây bộ điều phối lời gọi động.

Nếu coi mọi `Method` có cùng tên là cùng một khai báo nghiệp vụ, công cụ có thể hiển thị trùng, chọn nhầm phương thức hoặc tạo ánh xạ bị xung đột.

Ngược lại, nếu loại bỏ máy móc mọi phương thức do trình biên dịch hỗ trợ, công cụ phân tích bytecode hoặc theo dõi cách lời gọi được thực hiện lại có thể mất dữ liệu cần thiết.

Trước khi lọc, cần xác định mình muốn mô hình **khai báo nguồn** hay mô hình **phương thức trong đầu ra lúc chạy**.

## Bridge: cầu nối để bảo toàn đa hình

### Tình huống từ generic

Giả sử có khai báo:

```java
interface Converter<T> {
    T convert(T value);
}

class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value;
    }
}
```

Đây là đoạn minh họa độc lập về cấu trúc, chưa có chương trình chạy.

Ở mã nguồn, `StringConverter.convert(String)` triển khai hợp đồng `Converter<String>`. Nhưng sau xóa kiểu, phương thức của interface có dạng tham số `Object` và kết quả `Object`.

Để lời gọi qua hợp đồng sau xóa kiểu vẫn đến đúng phần thực thi, trình biên dịch có thể tạo một phương thức bridge trong lớp triển khai.

Có thể hình dung phần thân cầu nối như sau:

```java
// Mã giả mô tả nhiệm vụ của bridge, không phải phần cần tự thêm:
public Object convert(Object value) {
    return convert((String) value);
}
```

Bridge làm nhiệm vụ thích nghi chữ ký rồi chuyển tiếp đến phương thức cụ thể. Nó không phải một phương thức nghiệp vụ thứ hai mà người viết chủ động thiết kế.

Khi reflection liệt kê phương thức của `StringConverter`, có thể thấy cả:

- `convert(String)` trả `String`: phần khai báo cụ thể.
- `convert(Object)` trả `Object`: cầu nối được trình biên dịch tạo.

`Method.isBridge()` cho biết đâu là bridge. Không nhận diện bằng cách đoán tên phương thức: bridge thường giữ cùng tên với phương thức đích.

### Bridge không chỉ liên quan tham số generic

Cơ chế cầu nối còn có thể cần khi giữ hành vi ghi đè với kiểu trả về hiệp biến, tùy các chữ ký mà bản dịch phải hỗ trợ.

Do đó, không nên viết quy tắc “mọi bridge đều nhận Object” hoặc “chỉ lớp triển khai generic mới có bridge”. Ví dụ của bài dùng generic để tạo một trường hợp dễ quan sát.

Quy tắc dịch liên quan đến xóa kiểu và ghi đè được trình bày trong [JLS §8.4.8.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).

## Synthetic: phương thức hỗ trợ do công cụ tạo

`isSynthetic()` phản ánh dấu synthetic của phương thức. Nó thường giúp nhận ra các phương thức hỗ trợ không tương ứng với một khai báo phương thức được người viết nêu trực tiếp trong nguồn.

Bridge do `javac` tạo trong ví dụ sẽ có cả `isBridge() = true` và `isSynthetic() = true`.

Nhưng không được coi hai khái niệm là đồng nghĩa:

- Bridge có mục đích cụ thể là thích nghi quan hệ phương thức.
- Synthetic là dấu mang phạm vi rộng hơn về phần tử được sinh trong đầu ra.
- Một phương thức synthetic không nhất thiết là bridge.

Cũng không nên khẳng định mọi phương thức không được viết bằng tay đều phải synthetic. Ngôn ngữ có các thành viên được khai báo ngầm với quy tắc riêng; chẳng hạn không thể dùng định nghĩa đơn giản “không gõ trong nguồn = synthetic” cho mọi thành viên của enum.

Tên hỗ trợ như có dấu `$` hoặc các quy ước tên nội bộ không phải cách nhận diện ổn định. Hãy đọc cờ công khai thay vì suy luận từ tên hoặc phụ thuộc cách một phiên bản trình biên dịch đặt tên.

Quy tắc về biểu diễn nhị phân nằm tại [JLS §13.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.1).

## Varargs: cờ khai báo khác với kiểu mảng

Khai báo:

```java
public static String join(String prefix, String... parts)
```

có tham số cuối là varargs. Khi reflection đọc kiểu tham số, tham số đó vẫn có kiểu `String[]`.

Một phương thức khác viết:

```java
public static String joinArray(String prefix, String[] parts)
```

cũng có tham số cuối kiểu `String[]`, nhưng không được khai báo varargs.

Vì vậy:

| Phương thức | Kiểu tham số cuối qua getParameterTypes() | isVarArgs() |
| --- | --- | --- |
| `join(String, String...)` | `String[].class` | `true` |
| `joinArray(String, String[])` | `String[].class` | `false` |

Không suy ra varargs chỉ vì kiểu tham số cuối là mảng. Cũng không suy ra phương thức có ít nhất một tham số mảng ở đâu đó thì là varargs.

Trong mã Java, varargs là tham số cuối; khả năng gọi với nhiều đối số được trình biên dịch xử lý. Khi quét reflection, cờ `isVarArgs()` giữ lại thông tin về dạng khai báo.

`Parameter.isVarArgs()` có thể xác định riêng tham số varargs trong danh sách tham số.

## Các cờ trong class file và API đọc

Định dạng class file có các cờ như `ACC_BRIDGE`, `ACC_SYNTHETIC` và `ACC_VARARGS`. Reflection cung cấp các API để đọc ý nghĩa tương ứng mà không cần tự phân tích bit.

Xem mô tả tại [JVMS §4.6](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6) và [Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html).

Trong mã ứng dụng, ưu tiên `isBridge()`, `isSynthetic()`, `isVarArgs()`. Không diễn giải tùy ý giá trị bit của modifier bằng một hằng dùng cho loại thành viên khác: cùng một vị trí bit trong class file có thể mang ý nghĩa khác nhau tùy cấu trúc.

Các cờ là siêu dữ liệu của phương thức; chúng không tự cấp hoặc tước quyền gọi phương thức. Quyền truy cập và điều kiện gọi phản chiếu vẫn phải xét riêng.

## Chương trình đầy đủ

Ví dụ quan sát:

1. Hai phương thức `convert` trong đầu ra biên dịch.
2. Gọi bridge với đối số đúng và sai.
3. Sự khác nhau giữa varargs và tham số mảng thông thường.
4. Cách truyền đối số đúng khi gọi varargs bằng reflection.

Lưu thành `MethodFlagsDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Locale;

public class MethodFlagsDemo {
    interface Converter<T> {
        T convert(T value);
    }

    public static class StringConverter implements Converter<String> {
        @Override
        public String convert(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }

    public static class Operations {
        public static String join(String prefix, String... parts) {
            return prefix + String.join("|", parts);
        }

        public static String joinArray(String prefix, String[] parts) {
            return prefix + String.join("|", parts);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method[] methods = StringConverter.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(
                method -> method.getParameterTypes()[0].getSimpleName()));

        for (Method method : methods) {
            System.out.println(method.getName() + "("
                    + method.getParameterTypes()[0].getSimpleName()
                    + ")->" + method.getReturnType().getSimpleName()
                    + ":bridge=" + method.isBridge()
                    + ",synthetic=" + method.isSynthetic()
                    + ",varargs=" + method.isVarArgs());
        }

        Method bridge = StringConverter.class.getDeclaredMethod(
                "convert", Object.class);
        StringConverter target = new StringConverter();
        System.out.println("bridge.valid=" + bridge.invoke(target, "hello"));
        try {
            bridge.invoke(target, Integer.valueOf(7));
        } catch (InvocationTargetException ex) {
            System.out.println("bridge.invalid="
                    + ex.getCause().getClass().getSimpleName());
        }

        Method varargs = Operations.class.getDeclaredMethod(
                "join", String.class, String[].class);
        Method array = Operations.class.getDeclaredMethod(
                "joinArray", String.class, String[].class);
        System.out.println("join.varargs=" + varargs.isVarArgs());
        System.out.println("joinArray.varargs=" + array.isVarArgs());
        System.out.println("lastParameter.varargs="
                + varargs.getParameters()[1].isVarArgs());

        Object result = varargs.invoke(null,
                new Object[] {"p:", new String[] {"a", "b"}});
        System.out.println("reflective.result=" + result);
        try {
            varargs.invoke(null, "p:", "a", "b");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong.shape="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 MethodFlagsDemo.java
java MethodFlagsDemo
```

Kết quả với `javac` trên JDK 21:

```text
convert(Object)->Object:bridge=true,synthetic=true,varargs=false
convert(String)->String:bridge=false,synthetic=false,varargs=false
bridge.valid=HELLO
bridge.invalid=ClassCastException
join.varargs=true
joinArray.varargs=false
lastParameter.varargs=true
reflective.result=p:a|b
wrong.shape=IllegalArgumentException
```

Ví dụ sắp xếp hai phương thức của `StringConverter` theo tên kiểu tham số để output ổn định. Nó dựa trên cấu trúc đã cố định của lớp này: cả hai phương thức đều có một tham số. Khi mở rộng bộ quét cho đầu vào tùy ý, phải xử lý cả phương thức không có tham số và nhiều chữ ký khác nhau.

## Đọc kết quả bridge

### Vì sao có hai phương thức?

Trong mã nguồn chỉ viết một phần thực thi `convert(String)`. Bridge bổ sung dạng `convert(Object)` để hỗ trợ hợp đồng sau xóa kiểu.

Dòng thứ nhất cho biết bridge của ví dụ vừa được đánh dấu bridge vừa synthetic. Dòng thứ hai là phương thức cụ thể được viết trong nguồn.

Không có phương thức nào trong hai phương thức này là varargs. Generic và varargs là hai vấn đề riêng.

### Vì sao gọi bridge với Integer gây ClassCastException?

Ở mức chữ ký phản chiếu, bridge nhận `Object`, nên thao tác gọi có thể đưa vào một đối tượng `Integer`. Nhưng bên trong cầu nối cần chuyển đối tượng sang `String` để gọi phương thức cụ thể.

Phép chuyển đó thất bại. Vì lỗi phát sinh trong phương thức được gọi bằng reflection, nó được bọc trong `InvocationTargetException`. Chương trình đọc `getCause()` để in lỗi gốc `ClassCastException`.

Đây khác với lỗi truyền sai số lượng đối số trước khi phương thức được thực hiện.

Không nên gọi bridge như một cách vượt qua hợp đồng generic. Cầu nối bảo toàn cơ chế thực thi, không biến hợp đồng `Converter<String>` thành bộ chuyển đổi chấp nhận mọi đối tượng.

## Gọi varargs bằng reflection: phải giữ đúng hình dạng mảng

Phương thức đích:

```java
join(String prefix, String... parts)
```

có hai tham số ở mô hình phản chiếu: `String` và `String[]`.

Do đó, mã truyền vào `Method.invoke` một mảng hai phần tử:

```java
new Object[] {
    "p:",
    new String[] {"a", "b"}
}
```

- Phần tử 0 là đối số `prefix`.
- Phần tử 1 là một mảng `String[]` duy nhất cho `parts`.

Kết quả là `p:a|b`.

`Method.invoke` bản thân nó cũng có tham số varargs `Object... args`, nhưng đó là varargs của **API gọi phản chiếu**, khác với varargs của **phương thức đích**.

Lệnh:

```java
varargs.invoke(null, "p:", "a", "b");
```

truyền ba đối số cho một phương thức đích có hai vị trí tham số. Reflection không tự gom hai chuỗi cuối thành một `String[]` theo cách lời gọi Java trực tiếp `Operations.join("p:", "a", "b")` được trình biên dịch xử lý.

Vì vậy ví dụ nhận `IllegalArgumentException` cho hình dạng đối số sai.

Với phương thức đích chỉ có một tham số mảng tham chiếu, cũng phải chú ý tránh để mảng đó bị hiểu như chính mảng đối số của `Method.invoke`. Một cách rõ ràng là tạo `Object[]` chứa đúng một phần tử là mảng đích; cách khác thường dùng là ép mảng đích về `Object` khi truyền nó làm một đối số.

Không tự dùng `isVarArgs()` làm lý do rải hoặc gom mọi mảng ở bất kỳ vị trí nào. Nếu xây bộ gọi động hỗ trợ cú pháp thuận tiện như mã nguồn, thao tác gom đối số là phần bộ gọi đó phải định nghĩa và triển khai.

## Tìm phương thức bằng kiểu tham số sau xóa kiểu

Các lệnh tìm trong ví dụ dùng:

```java
StringConverter.class.getDeclaredMethod("convert", Object.class);
Operations.class.getDeclaredMethod(
        "join", String.class, String[].class);
```

Dòng đầu cố ý chọn bridge theo chữ ký nhận `Object`. Dòng thứ hai dùng `String[].class` vì varargs xuất hiện dưới dạng tham số mảng.

Không có cú pháp class literal `String....class`. Không tìm phương thức varargs bằng danh sách kiểu cho từng phần tử mà bạn định truyền khi gọi, như `String.class, String.class, String.class`.

Đối với các bridge liên quan kiểu trả về hiệp biến, có thể gặp những phương thức trùng tên và danh sách tham số nhưng khác kiểu trả về ở đầu ra class. Khi cần phân tích chính xác trường hợp đó, hãy xem toàn bộ các `Method` và kiểu trả về thay vì mặc nhiên coi tên cộng tham số là đủ để biểu diễn mọi thực thể nhị phân.

## Lọc phương thức theo mục tiêu của công cụ

Nếu tạo danh sách phương thức nguồn để người học đọc, một chính sách có thể bỏ bridge và các phương thức synthetic không cần hiển thị. Mảnh mã minh họa:

```java
if (method.isBridge() || method.isSynthetic()) {
    continue;
}
```

Mảnh này chỉ có ý nghĩa bên trong vòng lặp có biến `method`. Nó là một chính sách hiển thị có chủ đích, không phải quy tắc chung rằng các phương thức đó vô giá trị.

Nếu công cụ:

- Phân tích cách đa hình được thực hiện sau biên dịch, cần giữ bridge.
- Dựng ánh xạ từ phương thức bridge sang phương thức cụ thể, cần đọc bridge rồi phân giải.
- Đọc annotation cho hành vi framework, cần có quy tắc tìm nguồn và ưu tiên rõ ràng.
- Kiểm tra bytecode, cần phân biệt các cờ và toàn bộ chữ ký.

Không suy luận việc annotation có hay không chỉ từ cờ synthetic. Cách trình biên dịch hoặc công cụ khác xử lý siêu dữ liệu cần được kiểm tra theo đầu ra cụ thể; `isBridge()` không phải API tự trả về phương thức đích.

API [Class.getDeclaredMethods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getDeclaredMethods()) mô tả danh sách phương thức khai báo và không bảo đảm thứ tự cụ thể. Đừng chọn “phương thức đầu tiên có tên phù hợp” rồi kỳ vọng luôn là phương thức nguồn.

## Các giới hạn cần giữ rõ

- `isBridge() = true` không cho biết trực tiếp phần thân bridge hoặc phương thức mà nó chuyển tiếp.
- `isSynthetic() = true` không có nghĩa phương thức là private, không thể gọi hoặc chứa lỗi.
- `isSynthetic() = false` không có nghĩa mọi chi tiết đều do người viết gõ tường minh.
- `isVarArgs() = true` không có nghĩa phương thức tự nhận một số lượng đối số tùy ý qua mọi API.
- Tham số cuối là mảng không đủ chứng minh varargs.
- Cùng một quan hệ ghi đè không bắt buộc các khai báo ở các lớp khác nhau có cùng cờ varargs; cờ phản ánh khai báo của từng phương thức.

Khi đổi trình biên dịch, ngôn ngữ nguồn hoặc dùng công cụ sinh/biến đổi bytecode, chi tiết phương thức hỗ trợ có thể khác. Dùng các cờ và chữ ký thực tế mà API cung cấp, tránh gắn logic với tên phương thức nội bộ hoặc số lượng phương thức cố định.

## Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Cùng một tên phương thức xuất hiện hai lần | Kiểu tham số, kiểu trả về, isBridge và isSynthetic |
| Quét generic thấy phương thức nhận Object | Có thể là chữ ký sau xóa kiểu hoặc bridge; cần xét cờ và quan hệ |
| Tài liệu hiển thị trùng một thao tác | Chính sách lọc/phân giải cầu nối đã phù hợp chưa |
| Mọi phương thức cuối mảng đều bị coi varargs | Đọc isVarArgs thay vì chỉ nhìn kiểu mảng |
| Gọi varargs bằng reflection sai số đối số | Truyền một mảng cho vị trí varargs của phương thức đích |
| Lỗi từ bridge bị coi là lỗi của reflection | Xem nguyên nhân trong InvocationTargetException |
| Kết quả quét thay đổi thứ tự | Sắp xếp theo khóa phù hợp; không dựa vào thứ tự mặc định |

## Thực hành kiểm chứng

1. Chạy chương trình và đối chiếu hai phương thức `convert`.
2. In thêm `getGenericParameterTypes()` và `getGenericReturnType()` của hai phương thức để so sánh phần thực thi cụ thể với cầu nối.
3. Lọc các phương thức `isBridge()` trong bước hiển thị; giải thích vì sao phần nguồn còn một phương thức.
4. Đổi khai báo `join` từ `String... parts` thành `String[] parts`. Kiểu tham số vẫn là mảng nhưng `isVarArgs()` đổi thành `false`.
5. Giữ varargs, gọi phản chiếu với mảng rỗng cho `parts`; kết quả phải là `p:`.
6. Tách biệt ba nguyên nhân: đối số sai hình dạng, đối số gây lỗi chuyển kiểu bên trong bridge và lỗi thực sự của nghiệp vụ.

Điều cần nắm là **bridge hỗ trợ thích nghi phương thức, synthetic đánh dấu phần tử hỗ trợ trong đầu ra, còn varargs mô tả cách khai báo tham số biến đổi**. Nhận diện đúng giúp quét và gọi reflection mà không nhầm mô hình nguồn với mô hình sau biên dịch.
