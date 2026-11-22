# Wildcard giới hạn trên với ? extends T

## 1. Khi API cần đọc từ nhiều kiểu danh sách

Giả sử một hàm cần đọc các giá trị số để tính tổng theo `double`. Nếu nhận `List<Number>`, hàm không nhận trực tiếp được một biến `List<Integer>` hoặc `List<Double>`, dù `Integer` và `Double` đều là kiểu con của `Number`.

Nguyên nhân là các kiểu như `List<Integer>` và `List<Number>` có tính bất biến (invariance): quan hệ kế thừa giữa kiểu phần tử không tự tạo quan hệ kiểu con giữa hai lần tham số hóa đó.

Khi API chỉ cần lấy ra giá trị dùng được như `Number`, có thể khai báo:

```java
static double total(List<? extends Number> source) {
    double result = 0.0;
    for (Number value : source) {
        result += value.doubleValue();
    }
    return result;
}
```

Đây là đoạn phương thức minh họa, cần `import java.util.List;` và một lớp bao ngoài. Chương trình hoàn chỉnh có xử lý phần tử `null` ở mục 6.

`? extends Number` là **wildcard có giới hạn trên** (upper bounded wildcard). Nó nói rằng kiểu phần tử thực tế của danh sách là một kiểu chưa được nêu tên cụ thể, nhưng kiểu ấy là `Number` hoặc kiểu con của `Number`.

Nhờ vậy, `total` có thể nhận `List<Integer>`, `List<Double>` hoặc `List<Number>`. Mã trong hàm được bảo đảm có thể dùng phần tử đọc ra theo hợp đồng của `Number`.

Wildcard không đổi mọi danh sách thành `List<Number>` và không chuyển đổi các phần tử. Nó tạo một hợp đồng sử dụng cho phép đọc theo giới hạn trên đã biết.

## 2. Cách hiểu kiểu chưa biết

Với một biến:

```java
List<Integer> counts = new ArrayList<>();
List<? extends Number> view = counts;
```

Có thể hình dung `view` là `List<X>`, trong đó `X` là một kiểu chưa biết chính xác tại nơi dùng biến và có quan hệ `X` là kiểu con của hoặc chính `Number`.

Ta biết đủ để dùng một giá trị `X` như `Number`, nhưng không biết đủ để đưa một `Number` bất kỳ trở lại vào vị trí yêu cầu `X`.

Điều này không có nghĩa mọi phần tử phải có cùng lớp cụ thể lúc chạy. Một `List<Number>` chứa cả `Integer` và `Double` cũng phù hợp với `List<? extends Number>`: khi đó kiểu phần tử được khai báo là `Number`, còn các giá trị có thể thuộc những kiểu con khác nhau.

`?` biểu đạt phần thông tin kiểu chưa được nêu rõ trong hợp đồng sử dụng, không có nghĩa danh sách không có kiểu hay chương trình sẽ chọn kiểu tùy ý cho từng thao tác.

Đối chiếu định nghĩa wildcard tại [JLS §4.5.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1).

## 3. Đọc được theo T, không thêm tùy ý một T

### 3.1. Đọc theo giới hạn trên

```java
Number value = view.get(0);
double converted = value.doubleValue();
Object broad = view.get(0);
```

Với `List<? extends Number>`, kết quả đọc có thể được dùng như `Number` hoặc một kiểu cha phù hợp như `Object`. Không thể mặc định gán nó cho `Integer` chỉ vì ta đang nghĩ đến một danh sách đếm.

```java
// Integer narrow = view.get(0); // Lỗi biên dịch nếu bỏ chú thích
```

Kiểu tĩnh của `view` cũng có thể tham chiếu tới `List<Double>`. Khi cần giữ hợp đồng kết quả là `Integer`, hãy giữ và sử dụng một biến `List<Integer>` phù hợp hoặc thiết kế tham số kiểu có tên nối nguồn và đầu ra.

### 3.2. Vì sao không thêm Integer hay Double?

Các dòng sau đều không hợp lệ qua biến `view`:

```java
// view.add(4);
// view.add(2.5);
// view.set(0, Integer.valueOf(4));
```

Nếu danh sách thực tế là `List<Double>`, thêm `Integer` sẽ sai. Nếu danh sách thực tế là `List<Integer>`, thêm `Double` cũng sai. Chỉ biết một giá trị là `Number` không chứng minh nó thuộc đúng kiểu phần tử chưa biết của danh sách.

Đây là cơ chế ngăn làm hỏng hợp đồng của danh sách gốc. Trình biên dịch có thể nói đến `capture of ? extends Number` hoặc `CAP#1` trong chẩn đoán: nó đang đại diện kiểu chưa biết bằng một biến kiểu nội bộ để kiểm tra tính tương thích.

Đừng thêm phép ép kiểu danh sách hoặc che cảnh báo chỉ để vượt qua giới hạn này. Cần chọn đúng hợp đồng cho thao tác muốn thực hiện.

### 3.3. Ngoại lệ kiểu học là null

`null` có thể tương thích với kiểu tham chiếu chưa biết, nên `view.add(null)` hoặc `view.set(index, null)` có thể biên dịch về mặt kiểu. Nhưng thao tác thành công lúc chạy còn tùy danh sách có cho sửa và có chấp nhận `null` hay không.

Ví dụ `ArrayList` có thể nhận `null`; một danh sách không cho sửa có thể từ chối thao tác thay đổi. Quy tắc wildcard và chính sách của đối tượng danh sách là hai vấn đề khác nhau.

Không nên hiểu việc `null` được chấp nhận về kiểu là khuyến nghị đưa `null` vào dữ liệu. Nếu API không cho phần tử `null`, cần kiểm tra hoặc quy tắc dữ liệu riêng.

## 4. Không phải danh sách bất biến

Một hiểu nhầm phổ biến là gọi `List<? extends T>` là “danh sách chỉ đọc” theo nghĩa không thể thay đổi bất cứ thứ gì. Cách nói đó quá rộng.

Wildcard giới hạn trên chặn việc đưa một giá trị ngoài vào vị trí có kiểu phần tử chưa biết, nhưng nhiều thao tác thay đổi không cần một giá trị phần tử mới vẫn có thể hợp lệ:

| Thao tác qua `List<? extends Number>` | Kiểm tra kiểu | Điều kiện lúc chạy |
| --- | --- | --- |
| `get(index)` | Hợp lệ, dùng kết quả như `Number` | Chỉ số phải hợp lệ; giá trị có thể là `null` |
| `add(4)` | Bị từ chối | Không đến bước chạy |
| `set(index, 4)` | Bị từ chối | Không đến bước chạy |
| `add(null)` | Hợp lệ về kiểu | Danh sách phải cho thêm và chấp nhận `null` |
| `remove(index)` | Hợp lệ | Danh sách phải hỗ trợ xóa và chỉ số hợp lệ |
| `clear()` | Hợp lệ | Danh sách phải hỗ trợ thao tác tương ứng |

Ngoài ra, các thuật toán được thiết kế để giữ an toàn kiểu, chẳng hạn hoán đổi các phần tử đang có thông qua API phù hợp, có thể thay đổi thứ tự mà không thêm một giá trị ngoài không rõ kiểu. Không thể từ dấu `extends` kết luận rằng nội dung và thứ tự sẽ giữ nguyên.

Phép gán `List<? extends Number> view = counts` không sao chép danh sách. Nếu gọi `view.clear()` thành công, danh sách mà `counts` đang tham chiếu cũng bị xóa vì hai biến cùng trỏ tới một đối tượng.

Wildcard cũng không làm những đối tượng phần tử trở nên bất biến. Nếu giới hạn là một kiểu có phương thức thay đổi trạng thái, người đọc phần tử vẫn có thể gọi các phương thức được hợp đồng cho phép.

Hành vi tùy chọn của các thao tác sửa đổi được nêu trong tài liệu [List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html).

## 5. Dùng ? extends T trong API có tham số kiểu

Giới hạn wildcard có thể dùng một kiểu cụ thể như `Number`, hoặc dùng một tham số kiểu đã khai báo như `T`:

```java
static <T> List<T> editableCopy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

`<T>` khai báo tham số kiểu có tên của phương thức. `? extends T` cho phép nguồn có kiểu phần tử là `T` hoặc một kiểu con phù hợp, còn kết quả là một danh sách mới có hợp đồng phần tử `T`.

```java
List<Integer> counts = List.of(1, 2, 3);
List<Number> copy = editableCopy(counts);
copy.add(2.5);
```

Trong ngữ cảnh này có thể chọn `T = Number`; nguồn `List<Integer>` đáp ứng quan hệ giới hạn trên. Bản sao là một `ArrayList` mới theo hợp đồng `List<Number>`, nên có thể thêm một `Double` vào bản sao mà không làm danh sách số nguyên nguồn vi phạm kiểu.

Đây là sao chép danh sách chứa các tham chiếu phần tử, không phải sao chép sâu từng đối tượng phần tử. Những phần tử có trạng thái sửa đổi được vẫn có thể được chia sẻ giữa nguồn và bản sao.

Phân biệt các chữ ký gần giống nhau:

| Chữ ký | Ý nghĩa chính |
| --- | --- |
| `void inspect(List<Number> values)` | Yêu cầu đúng một danh sách theo hợp đồng `Number`; không nhận trực tiếp biến `List<Integer>` |
| `void inspect(List<? extends Number> values)` | Nhận nguồn số với kiểu phần tử tương thích; đọc ra theo `Number` |
| `<N extends Number> N head(List<N> values)` | Đặt tên `N` để nối kiểu phần tử nguồn với kiểu trả về |
| `<T> List<T> editableCopy(List<? extends T> values)` | Chấp nhận nguồn phù hợp và tạo danh sách kết quả theo `T` |

Các dòng bảng minh họa chữ ký. Chọn wildcard khi không cần gọi tên kiểu phần tử chính xác nhưng cần một giới hạn để sử dụng nó. Chọn tham số kiểu có tên khi phải nối quan hệ giữa nhiều vị trí trong API. Hai cách có thể kết hợp như `editableCopy`.

Trong quy tắc thiết kế thường được gọi là PECS, phần “Producer Extends” gợi ý dùng `extends` cho nguồn cung cấp giá trị. Cần hiểu đây là vai trò trong một thao tác cụ thể, không phải lời hứa rằng đối tượng nguồn bất biến.

## 6. Chương trình chạy đầy đủ

Lưu thành `UpperWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class UpperWildcardDemo {
    static double total(List<? extends Number> source) {
        double result = 0.0;
        for (Number value : source) {
            result += Objects.requireNonNull(value, "element").doubleValue();
        }
        return result;
    }

    static <T> List<T> editableCopy(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<Integer> counts = new ArrayList<>(List.of(1, 2, 3));
        List<Double> measurements = List.of(1.5, 2.5);
        System.out.println("counts total=" + total(counts));
        System.out.println("measurements total=" + total(measurements));

        List<? extends Number> view = counts;
        Number first = view.get(0);
        System.out.println("first=" + first);

        List<Number> copy = editableCopy(counts);
        copy.add(2.5);
        System.out.println("copy=" + copy);

        view.remove(0);
        System.out.println("counts after remove=" + counts);
        view.clear();
        System.out.println("counts after clear=" + counts);

        List<Integer> nullable = new ArrayList<>();
        List<? extends Number> nullableView = nullable;
        nullableView.add(null);
        System.out.println("nullable=" + nullable);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror UpperWildcardDemo.java
java UpperWildcardDemo
```

Stdout:

```text
counts total=6.0
measurements total=4.0
first=1
copy=[1, 2, 3, 2.5]
counts after remove=[2, 3]
counts after clear=[]
nullable=[null]
```

Hai danh sách có kiểu phần tử khác nhau đều vào được `total`. Biến `view` đọc theo `Number`, còn các thao tác `remove` và `clear` cho thấy wildcard không tạo một bản sao hoặc khóa nội dung danh sách.

`copy` là danh sách riêng: thêm `2.5` không đưa số thực vào `counts`. Dòng cuối chỉ minh họa rằng giá trị `null` đi qua được kiểm tra kiểu và được `ArrayList` chấp nhận; không truyền danh sách đó vào `total` vì phần triển khai tổng yêu cầu phần tử khác `null`.

Phép tính tổng chủ động dùng biểu diễn `double`. Chuyển đổi từ các kiểu `Number` khác có thể mất độ chính xác; wildcard chỉ quyết định tính tương thích kiểu, không định nghĩa một cơ chế số học chính xác cho mọi loại số.

## 7. Lỗi cần tránh

### 7.1. Nhầm ? extends T với một lớp có tên T

`?` không phải tên mà ta có thể dùng làm kiểu biến cục bộ hay kiểu trả về của một phương thức khác. Khi cần một tên để nối nhiều vị trí, khai báo tham số kiểu như `<T>`.

Cũng không khai báo biến bằng `? extends Number value`. Wildcard xuất hiện làm đối số kiểu trong những vị trí phù hợp như `List<? extends Number>`; nó không thay thế trực tiếp một kiểu khai báo biến thông thường.

### 7.2. Mỗi wildcard không mặc nhiên cùng kiểu chưa biết

Hai tham số đều có dạng `List<? extends Number>` không bảo đảm chúng có cùng kiểu phần tử chính xác: một bên có thể là `List<Integer>`, bên kia là `List<Double>`. Vì thế không được tùy ý đọc một phần tử bên này rồi thêm sang bên kia.

Nếu thuật toán cần quan hệ chung giữa các nguồn/đích, phải diễn đạt bằng tham số kiểu có tên và giới hạn phù hợp, thay vì chỉ viết hai wildcard trông giống nhau.

### 7.3. Đừng gọi set bằng một Number vừa đọc ra để lách kiểm tra

Đọc `Number item = view.get(0)` chỉ giữ hợp đồng `Number` ở biến `item`. Nó không biến `item` thành một giá trị có thể truyền lại cho mọi kiểu phần tử mà `view` có thể đại diện.

Khi cần thao tác giữ nguyên kiểu phần tử chưa biết, một phương thức trợ giúp generic có thể nắm bắt wildcard một cách an toàn. Đó là cơ chế nắm bắt kiểu (capture conversion), không phải ép danh sách sang một kiểu rộng hơn.

Quy tắc nắm bắt wildcard được mô tả tại [JLS §5.1.10](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10).

### 7.4. Không biến wildcard thành hợp đồng trả về mặc định

Nếu API có thể trả về một `List<Integer>` cụ thể và người gọi cần giữ thông tin ấy, không nên tự mở rộng kết quả thành `List<? extends Number>` mà không có lý do. Kiểu trả về có wildcard có thể làm người gọi mất những thao tác kiểu cụ thể vốn hợp lệ.

Dùng wildcard ở nơi nó giải quyết một yêu cầu tương thích thực tế, thường là tham số nhận nguồn. Không thay mọi kiểu cụ thể bằng wildcard chỉ vì muốn API trông tổng quát hơn.

## 8. Tự kiểm tra

1. `List<? extends Number>` có thể tham chiếu tới một biến `List<Integer>` không?
2. Đọc `get(0)` qua kiểu đó được bảo đảm dùng như kiểu nào?
3. Vì sao không thêm được `Integer` qua biến wildcard, dù đối tượng thực tế đang là `List<Integer>`?
4. `clear()` có thể làm thay đổi danh sách gốc không?
5. Hai biến `List<? extends Number>` có chắc cùng một kiểu phần tử chưa biết không?

Đáp án:

1. Có. `Integer` phù hợp với giới hạn trên `Number`.
2. `Number` hoặc một kiểu cha phù hợp; không mặc định là `Integer`.
3. Thao tác được kiểm tra theo kiểu tĩnh chứa wildcard; hợp đồng đó không nêu rõ kiểu phần tử là `Integer` và cũng có thể đại diện một danh sách số khác.
4. Có nếu đối tượng hỗ trợ xóa; phép gán wildcard không sao chép danh sách.
5. Không. Mỗi nguồn có thể có một kiểu phần tử phù hợp khác nhau.

Khi thấy `? extends T`, hãy nghĩ đến một nguồn có kiểu phần tử chưa biết nhưng đọc được theo `T`. Sau đó kiểm tra riêng thao tác sửa đổi, chính sách `null` và việc các biến có đang chia sẻ cùng đối tượng hay không.
