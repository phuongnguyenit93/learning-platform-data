# Trải và gom đối số tại vị trí chỉ định với MethodHandle

Java 9 mở rộng API `MethodHandle` với các overload cho phép trải (spread) hoặc gom (collect) đối số bắt đầu tại một vị trí cụ thể trong danh sách tham số. Các thao tác này giúp chuyển đổi hình dạng lời gọi mà không phải viết adapter method cho từng tổ hợp tham số.

Ba cơ chế cần phân biệt:

- `asSpreader(pos, arrayType, arrayLength)`: nhận một array tại vị trí chỉ định rồi trải các phần tử của array thành nhiều đối số cho method handle gốc.
- `asCollector(pos, arrayType, arrayLength)`: nhận nhiều đối số riêng tại vị trí chỉ định, gom chúng thành một array rồi gọi method handle gốc.
- `MethodHandles.collectArguments(target, pos, filter)`: gọi một method handle filter với một nhóm đối số, rồi đưa kết quả của filter vào tham số của target tại vị trí chỉ định.

Các API này thao tác trên kiểu lời gọi của MethodHandle. Chúng hữu ích khi xây dựng adapter, pipeline gọi động, bộ định tuyến lời gọi hoặc lớp tích hợp giữa API dùng array và API dùng tham số riêng lẻ.

## 1. MethodHandle và MethodType

`MethodHandle` là tham chiếu có kiểu tới một phương thức, constructor hoặc thao tác có thể gọi. Mỗi handle có một `MethodType` mô tả kiểu trả về và danh sách kiểu tham số:

~~~java
MethodType type = handle.type();
~~~

Ví dụ, một handle tới phương thức static:

~~~java
static String render(String prefix, int left, int right, String suffix) {
    return prefix + (left + right) + suffix;
}
~~~

có kiểu:

~~~text
(String, int, int, String)String
~~~

Ký hiệu này nghĩa là handle nhận bốn đối số theo thứ tự String, int, int, String và trả về String.

Có thể tạo handle bằng `MethodHandles.Lookup.findStatic`:

~~~java
MethodHandle render = MethodHandles.lookup().findStatic(
    Example.class,
    "render",
    MethodType.methodType(
        String.class,
        String.class, int.class, int.class, String.class
    )
);
~~~

Kiểu truyền vào `findStatic` phải khớp với chữ ký phương thức. Nếu không tìm thấy phương thức hoặc không có quyền truy cập, quá trình tra cứu thất bại với ngoại lệ tương ứng.

Với handle tới phương thức instance, receiver là tham số đầu tiên trong MethodType. Vì vậy, chỉ số vị trí của các thao tác spread/collect tính cả receiver đó.

## 2. Trải đối số bằng asSpreader

Chữ ký positional:

~~~java
MethodHandle asSpreader(
    int pos,
    Class<?> arrayType,
    int arrayLength
)
~~~

`asSpreader` tạo một handle mới có kiểu lời gọi thay đổi như sau:

1. Handle gốc nhận một dãy `arrayLength` tham số riêng biệt bắt đầu từ vị trí `pos`.
2. Handle mới thay cả dãy tham số đó bằng một tham số kiểu array `arrayType`.
3. Khi gọi handle mới, các phần tử của array được trải ra và truyền vào các vị trí tương ứng của handle gốc.

Ví dụ handle gốc có kiểu:

~~~text
(String, int, int, String)String
~~~

Dùng:

~~~java
MethodHandle spread = render.asSpreader(1, int[].class, 2);
~~~

Handle mới có kiểu:

~~~text
(String, int[], String)String
~~~

Hai tham số int ở vị trí 1 và 2 đã được thay bằng một tham số int[] tại vị trí 1. Khi gọi:

~~~java
String result = (String) spread.invokeWithArguments(
    "sum=", new int[] {4, 5}, "!"
);
~~~

array được trải thành hai đối số int cho phương thức render ban đầu. Kết quả là `sum=9!`.

### Ý nghĩa của pos và arrayLength

- `pos` là chỉ số bắt đầu của nhóm tham số trong MethodType của handle gốc, đánh số từ 0.
- `arrayLength` là số tham số liên tiếp sẽ được thay bằng một array argument.
- `arrayType` phải là kiểu array có component type tương thích với nhóm tham số cần trải.

Ví dụ trên có pos = 1 vì tham số đầu tiên là prefix. Hai tham số int liên tiếp được trải nên arrayLength = 2.

Overload cũ:

~~~java
handle.asSpreader(arrayType, arrayLength)
~~~

áp dụng cho nhóm tham số ở cuối chữ ký. Overload có pos cho phép chọn một vị trí ở giữa danh sách tham số, giữ nguyên các tham số nằm trước và sau nhóm được trải.

## 3. Gom đối số bằng asCollector

Chữ ký positional:

~~~java
MethodHandle asCollector(
    int pos,
    Class<?> arrayType,
    int arrayLength
)
~~~

`asCollector` thực hiện hướng chuyển đổi ngược với `asSpreader`:

1. Handle gốc có một tham số kiểu array tại vị trí `pos`.
2. Handle mới thay tham số array đó bằng `arrayLength` tham số riêng lẻ có kiểu component của array.
3. Khi gọi handle mới, các đối số riêng lẻ được gom thành một array rồi truyền vào handle gốc.

Giả sử phương thức nhận array:

~~~java
static String renderArray(String prefix, int[] values, String suffix) {
    return prefix + (values[0] + values[1]) + suffix;
}
~~~

Handle gốc có kiểu:

~~~text
(String, int[], String)String
~~~

Dùng:

~~~java
MethodHandle collector =
    renderArray.asCollector(1, int[].class, 2);
~~~

Handle mới có kiểu:

~~~text
(String, int, int, String)String
~~~

Khi gọi:

~~~java
String result = (String) collector.invokeWithArguments(
    "sum=", 4, 5, "!"
);
~~~

hai đối số int được gom thành một int[] rồi truyền vào renderArray. Kết quả vẫn là `sum=9!`.

### Chọn arrayType và số phần tử

- `arrayType` phải là kiểu array mà tham số của handle gốc có thể nhận.
- Component type của array phải tương thích với kiểu các đối số được gom.
- `arrayLength` xác định số phần tử của array được tạo cho mỗi lần gọi.
- `pos` phải trỏ tới tham số array trong chữ ký của handle gốc.

Overload cũ:

~~~java
handle.asCollector(arrayType, arrayLength)
~~~

áp dụng cho tham số array ở cuối chữ ký. Overload có pos cho phép gom đối số tại vị trí bất kỳ phù hợp, kể cả khi handle còn các tham số khác ở phía sau.

## 4. So sánh asSpreader và asCollector

| Đặc điểm | asSpreader | asCollector |
|---|---|---|
| Chữ ký handle gốc | Nhiều tham số riêng | Một tham số array |
| Chữ ký handle mới | Một tham số array | Nhiều tham số riêng |
| Hướng chuyển đổi | Array thành các đối số | Các đối số thành array |
| Vị trí | `pos` là đầu nhóm tham số gốc | `pos` là vị trí tham số array gốc |
| Số lượng | `arrayLength` phần tử được trải | `arrayLength` phần tử được gom |

Có thể xem chúng là hai adapter đối xứng về hình dạng đối số:

~~~text
asSpreader:
(String, int, int, String)
          |
          | trải hai int từ array
          v
(String, int[], String)

asCollector:
(String, int[], String)
          |
          | gom hai int thành array
          v
(String, int, int, String)
~~~

Cả hai tạo một MethodHandle mới; handle ban đầu vẫn tồn tại và không bị sửa đổi.

## 5. collectArguments: chạy filter và chèn kết quả

`MethodHandles.collectArguments` là một combinator khác với `MethodHandle.asCollector`.

Chữ ký:

~~~java
MethodHandle collectArguments(
    MethodHandle target,
    int pos,
    MethodHandle filter
)
~~~

Với filter trả về giá trị khác void:

1. Các đối số ở vùng tương ứng được truyền cho filter.
2. Filter chạy và trả về một giá trị.
3. Giá trị trả về được đưa vào tham số của target tại vị trí `pos`.
4. Các tham số còn lại của target được lấy từ lời gọi của handle mới.

Ví dụ có hai phương thức:

~~~java
static int add(int left, int right) {
    return left + right;
}

static String format(String prefix, int total, String suffix) {
    return prefix + total + suffix;
}
~~~

Handle `format` có kiểu:

~~~text
(String, int, String)String
~~~

Handle `add` có kiểu:

~~~text
(int, int)int
~~~

Tạo handle kết hợp:

~~~java
MethodHandle combined =
    MethodHandles.collectArguments(format, 1, add);
~~~

Filter `add` trả về int và kết quả được chèn vào tham số thứ hai của format (vị trí 1). Handle mới có kiểu:

~~~text
(String, int, int, String)String
~~~

Khi gọi:

~~~java
String result = (String) combined.invokeWithArguments(
    "sum=", 4, 5, "!"
);
~~~

thứ tự xử lý là:

1. Giữ prefix `sum=` cho tham số đầu của format.
2. Gọi add(4, 5), nhận kết quả 9.
3. Đưa 9 vào tham số total của format.
4. Truyền suffix `!` vào tham số cuối của format.

Kết quả là `sum=9!`.

### Khác biệt với filterArguments

`MethodHandles.filterArguments` áp dụng filter vào một hoặc nhiều tham số tương ứng của target, thường theo quan hệ một filter cho một vị trí tham số.

`collectArguments` cho phép một filter nhận nhiều đối số đầu vào và tạo ra một giá trị để thay cho một tham số của target. Vì vậy, nó phù hợp khi cần kết hợp hoặc tính toán dữ liệu trước khi gọi target.

### Khác biệt với asCollector

- `asCollector` chỉ gom nhiều đối số thành một array rồi truyền array vào handle gốc.
- `collectArguments` gọi một filter tùy ý; filter có thể tính tổng, chuyển đổi, tra cứu hoặc tạo đối tượng rồi trả kết quả cho target.

Nếu chỉ cần đóng gói các giá trị vào array, dùng asCollector. Nếu cần chạy logic để tạo giá trị tham số, dùng collectArguments.

## 6. Vị trí tham số và receiver của instance method

Chỉ số `pos` luôn tính trên danh sách tham số của MethodHandle, không tính theo vị trí tên tham số trong mã nguồn.

Với static method:

~~~java
static String render(String prefix, int left, int right, String suffix)
~~~

các vị trí là:

| pos | Tham số |
|---:|---|
| 0 | prefix |
| 1 | left |
| 2 | right |
| 3 | suffix |

Với handle tới instance method:

~~~java
class Calculator {
    int add(int left, int right) {
        return left + right;
    }
}
~~~

MethodHandle được tạo bởi `findVirtual` có receiver làm tham số đầu tiên:

~~~text
(Calculator, int, int)int
~~~

Do đó:

- pos 0 là receiver Calculator.
- pos 1 là left.
- pos 2 là right.

Nếu muốn trải hai đối số int, dùng pos = 1. Nếu dùng pos = 0, bạn đang tác động tới vị trí receiver và array component type phải tương thích với vị trí đó; thường đây không phải điều mong muốn.

Hãy kiểm tra `handle.type()` trước khi chọn pos, đặc biệt khi làm việc với handle được tạo động hoặc handle đã qua nhiều bước adaptation.

## 7. Kiểm tra kiểu, arity và lỗi thường gặp

Các combinator kiểm tra MethodType khi tạo handle mới. Một số điều kiện cần thỏa:

- `pos` nằm trong phạm vi tham số phù hợp.
- `arrayType` là một array class.
- `arrayLength` không âm và không vượt quá số tham số có thể thay đổi.
- Với asSpreader, component type của array tương thích với nhóm tham số đích.
- Với asCollector, tham số target tại pos phải nhận arrayType.
- Với collectArguments, kiểu trả về của filter phải tương thích với tham số target tại pos; các tham số filter phải khớp vùng đối số của handle mới.

Nếu cấu trúc kiểu không thể tạo được, việc adaptation có thể thất bại với `IllegalArgumentException` hoặc `WrongMethodTypeException`, tùy lỗi cụ thể. Lỗi tra cứu method handle có thể phát sinh `NoSuchMethodException` hoặc `IllegalAccessException`.

Khi gọi handle, các lỗi thực thi của phương thức đích có thể được ném ra như bình thường. Các API gọi động như `invokeWithArguments` khai báo ném Throwable, vì vậy caller cần xử lý hoặc khai báo ngoại lệ phù hợp.

### Kiểm tra MethodType sau mỗi bước

~~~java
MethodHandle adapted = target.asSpreader(1, int[].class, 2);
System.out.println(adapted.type());
~~~

Không đoán kiểu sau adaptation. Hãy kiểm tra `type()` và đối chiếu với cách gọi thực tế.

Nếu cần chuyển đổi kiểu ngoài việc trải/gom đối số, có thể dùng `asType(newType)` khi các chuyển đổi được MethodHandle hỗ trợ. `asType` không thể biến hai chữ ký hoàn toàn không tương thích thành một lời gọi hợp lệ.

## 8. Varargs và fixed arity

MethodHandle trỏ tới một phương thức varargs có thể mang đặc tính variable-arity collector. Khi đó, cơ chế gọi có thể tự gom các đối số cuối thành array theo kiểu varargs.

~~~java
static String join(String separator, String... values) {
    return String.join(separator, values);
}
~~~

Nếu muốn gọi đúng theo chữ ký cố định có tham số array, dùng:

~~~java
MethodHandle fixed = handle.asFixedArity();
~~~

`asFixedArity()` tạo handle có cách gọi fixed-arity, không tự động thu gom các đối số cuối theo quy tắc variable arity.

Khi đang học hoặc xây dựng adapter, nên dùng `asSpreader(pos, arrayType, length)` và `asCollector(pos, arrayType, length)` để biểu diễn rõ số lượng và vị trí đối số cần chuyển đổi. Điều đó giúp tránh nhầm lẫn giữa adaptation tường minh và hành vi varargs tự động.

## 9. Kết hợp nhiều bước adaptation

Các adaptation có thể nối tiếp nhau. Ví dụ, trước tiên trải một array thành đối số riêng, sau đó đổi kiểu nếu cần:

~~~java
MethodHandle spread = target.asSpreader(1, int[].class, 2);
MethodHandle adapted = spread.asType(
    MethodType.methodType(
        String.class, String.class, int[].class, String.class
    )
);
~~~

Khi nối nhiều combinator:

1. Kiểm tra kiểu handle ban đầu.
2. Áp dụng một adaptation.
3. Kiểm tra lại `type()`.
4. Xác định thứ tự đối số của handle mới.
5. Chỉ tiếp tục bước kế tiếp khi kiểu mới khớp với mục tiêu.

Mỗi combinator tạo handle mới. Việc nối nhiều bước không sửa handle ban đầu nhưng có thể làm chữ ký cuối cùng khó đọc. Nên giữ các biến trung gian có tên thể hiện vai trò như `spread`, `collector` hoặc `combined`.

## 10. Ví dụ Java chạy được

Ví dụ dưới đây minh họa cả ba cơ chế:

- `asSpreader`: chuyển hai tham số int thành một int[].
- `asCollector`: chuyển một int[] thành hai tham số int.
- `collectArguments`: gọi filter add để tính tổng rồi chèn tổng vào format.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodHandleCollectExample {
    public static String render(String prefix, int left, int right,
            String suffix) {
        return prefix + (left + right) + suffix;
    }

    public static String renderArray(String prefix, int[] values,
            String suffix) {
        return prefix + (values[0] + values[1]) + suffix;
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static String format(String prefix, int total, String suffix) {
        return prefix + total + suffix;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle render = lookup.findStatic(
            MethodHandleCollectExample.class,
            "render",
            MethodType.methodType(
                String.class, String.class, int.class, int.class, String.class
            )
        );

        MethodHandle spread = render.asSpreader(1, int[].class, 2);
        System.out.println("spread type=" + spread.type());
        System.out.println("spread result="
            + spread.invokeWithArguments("sum=", new int[] {4, 5}, "!"));

        MethodHandle renderArray = lookup.findStatic(
            MethodHandleCollectExample.class,
            "renderArray",
            MethodType.methodType(
                String.class, String.class, int[].class, String.class
            )
        );

        MethodHandle collector = renderArray.asCollector(1, int[].class, 2);
        System.out.println("collector type=" + collector.type());
        System.out.println("collector result="
            + collector.invokeWithArguments("sum=", 4, 5, "!"));

        MethodHandle add = lookup.findStatic(
            MethodHandleCollectExample.class,
            "add",
            MethodType.methodType(int.class, int.class, int.class)
        );
        MethodHandle format = lookup.findStatic(
            MethodHandleCollectExample.class,
            "format",
            MethodType.methodType(
                String.class, String.class, int.class, String.class
            )
        );

        MethodHandle combined = MethodHandles.collectArguments(format, 1, add);
        System.out.println("collectArguments type=" + combined.type());
        System.out.println("collectArguments result="
            + combined.invokeWithArguments("sum=", 4, 5, "!"));
    }
}
~~~

Lưu trong tệp `MethodHandleCollectExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all MethodHandleCollectExample.java
java MethodHandleCollectExample
~~~

Kết quả stdout chính xác:

~~~text
spread type=(String,int[],String)String
spread result=sum=9!
collector type=(String,int,int,String)String
collector result=sum=9!
collectArguments type=(String,int,int,String)String
collectArguments result=sum=9!
~~~

Phân tích kết quả:

1. Handle spread thay hai tham số int bằng một int[] tại vị trí 1.
2. Handle collector thay tham số int[] bằng hai tham số int tại vị trí 1.
3. collectArguments gọi add(4, 5), rồi chèn giá trị 9 vào tham số total của format.
4. Cả ba handle mới đều có kiểu và kết quả được in ra đúng với hợp đồng adaptation.

## 11. Lỗi thường gặp

- **Nhầm chiều chuyển đổi:** asSpreader nhận array để gọi target có nhiều tham số; asCollector nhận nhiều tham số để gọi target có array.
- **Nhầm asCollector với collectArguments:** một bên tạo array; bên còn lại gọi filter và chèn kết quả vào target.
- **Dùng pos theo vị trí tham số nguồn trong mã mà quên receiver:** với instance method, receiver là tham số đầu của MethodHandle.
- **Chọn arrayType không tương thích:** component type phải phù hợp với các tham số được trải hoặc gom.
- **Chọn arrayLength sai:** số lượng phần tử phải khớp với vùng tham số cần chuyển đổi.
- **Giả định overload không có pos có thể xử lý mọi vị trí:** overload cũ thao tác ở cuối chữ ký; dùng overload positional để chọn vị trí giữa.
- **Không kiểm tra type() sau adaptation:** mỗi bước có thể thay đổi arity và thứ tự tham số.
- **Dùng collectArguments khi chỉ cần đóng gói array:** asCollector diễn đạt đúng ý định hơn.
- **Dùng asCollector khi cần tính toán giá trị:** dùng collectArguments với filter phù hợp.
- **Nhầm varargs với collector tường minh:** dùng asFixedArity khi cần chữ ký array cố định.
- **Bỏ qua Throwable khi gọi động:** invokeWithArguments có thể ném lỗi từ phương thức đích và lỗi liên kết lời gọi.
- **Dùng MethodHandle adaptation như một cách bỏ qua quyền truy cập:** Lookup vẫn kiểm tra quyền khi tạo handle.

## 12. Tài liệu tham khảo chính thức

- [MethodHandle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): kiểu handle, asSpreader, asCollector, asFixedArity và invokeWithArguments.
- [MethodHandles — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): collectArguments, filterArguments, Lookup và các combinator.
- [MethodType — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn kiểu trả về và danh sách tham số.
- [JEP 274: Enhanced Method Handles](https://openjdk.org/jeps/274): các cải tiến cho MethodHandle combinators được đưa vào Java 9.