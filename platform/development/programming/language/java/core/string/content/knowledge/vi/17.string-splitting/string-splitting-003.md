# Giữ hoặc bỏ trường rỗng cuối khi tách chuỗi

Với chuỗi `"Lan,Java,,"`, hai dấu phẩy cuối có thể thể hiện **hai cột đang rỗng**. Nếu bỏ chúng, bản ghi bốn cột bị biến thành bản ghi hai cột. Quy tắc `limit` đã được học ở bài trước; bài này tập trung vào **tác động với dữ liệu có cấu trúc**, cách kiểm tra số trường và việc phân biệt rỗng với trắng.

## 1. Không được nhầm trường rỗng với trường thiếu

| Đầu vào | `split(",")` | `split(",", -1)` |
| --- | --- | --- |
| `"Lan,Java,,"` | `["Lan", "Java"]` | `["Lan", "Java", "", ""]` |
| `"A,B,"` | `["A", "B"]` | `["A", "B", ""]` |
| `"A,,C,"` | `["A", "", "C"]` | `["A", "", "C", ""]` |
| `",,"` | Mảng độ dài 0 | Ba phần `""` |
| `""` | Một phần `""` | Một phần `""` |

`split(regex)` dùng `limit=0`, nên **mọi** phần rỗng cuối bị loại; `split(regex, -1)` giữ chúng. Những phần rỗng ở đầu và giữa vẫn tồn tại nếu không nằm trong chính đoạn đuôi bị loại.

Khi thử dữ liệu rỗng, in `parts.length` và chỉ số từng trường. `Arrays.toString` không thêm dấu nháy quanh chuỗi rỗng; nhìn `[]` thôi dễ nhầm mảng rỗng với mảng một phần tử rỗng.

## 2. Ví dụ kiểm tra schema bốn cột

Lưu thành `PreserveColumnsDemo.java` (JDK 17+):

```java
public class PreserveColumnsDemo {
    public static void main(String[] args) {
        String input = "Lan,Java,,";
        String[] defaultParts = input.split(",");
        String[] fields = input.split(",", -1);

        System.out.println("default=" + defaultParts.length);
        System.out.println("preserved=" + fields.length);
        for (int i = 0; i < fields.length; i++) {
            System.out.println(i + ": [" + fields[i] + "]");
        }
        if (fields.length != 4) {
            throw new IllegalArgumentException("Expected four columns");
        }

        String name = fields[0];
        String language = fields[1];
        String level = fields[2];
        String note = fields[3];
        System.out.println(name + ": " + language);
        System.out.println(level.isEmpty() && note.isEmpty());

        System.out.println(input.equals(String.join(",", fields)));
        System.out.println(input.equals(String.join(",", defaultParts)));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PreserveColumnsDemo.java
java PreserveColumnsDemo
```

```text
default=2
preserved=4
0: [Lan]
1: [Java]
2: []
3: []
Lan: Java
true
true
false
```

Với delimiter literal đơn ký tự `","`, `String.join(",", input.split(",", -1))` dựng lại nguyên chuỗi bao gồm các dấu cuối; bản `split(",")` đã làm mất chúng. Không suy rộng tính chất khôi phục nguyên văn cho mọi regex vì regex có thể khớp nhiều kiểu hoặc nhiều ký tự khác nhau.

## 3. `""` khác `" "` và khác trường không hiện diện

`"A, ,"` dùng `split(",", -1)` cho `["A", " ", ""]`. Trường thứ hai chứa **một dấu cách**, còn trường thứ ba có độ dài bằng 0:

```java
String[] fields = "A, ,".split(",", -1);
System.out.println(fields[1].isEmpty()); // false
System.out.println(fields[1].isBlank()); // true
System.out.println(fields[2].isEmpty()); // true
```

`strip()`, `trim()` hoặc `isBlank()` có thể hữu ích khi quy tắc dữ liệu cho phép chuẩn hóa khoảng trắng, nhưng không được áp dụng vô điều kiện vào dữ liệu cần bảo toàn giá trị gốc.

Bản ghi `"A,B"` có hai trường, còn `"A,B,"` có trường thứ ba tồn tại nhưng rỗng. Nếu định dạng yêu cầu ba cột, giữ chúng bằng `-1`, xác minh `parts.length==3`, sau đó mới kiểm tra từng giá trị bắt buộc. `split` không tự xác thực schema.

## 4. Chọn chính sách xử lý

Dùng `-1` khi cần đếm đúng số cột, ánh xạ đối tượng, khôi phục dữ liệu hoặc ghi nhận trường trống cuối. Dùng mặc định nếu định dạng cho phép **cố ý bỏ** phần rỗng cuối. Với dấu phân cách nguyên văn như `|` hay `.`, có thể kết hợp `Pattern.quote(delimiter)` cùng `-1`.

Cả hai cách đều chưa đủ để đọc **CSV có dấu nháy**: dấu phẩy bên trong trường được nháy cần parser CSV. Trường rỗng cuối chỉ là một trong nhiều yêu cầu của parser.

## Tự kiểm tra

1. `"x,y,,".split(",", -1)` có mấy phần và các phần cuối là gì?
2. Vì sao `",,".split(",")` có `length=0` còn `"".split(",")` có `length=1`?
3. Cần bốn cột từ `"id,name,note,"` thì chọn overload nào?
4. `"A, ,"` có hai trường cuối giống nhau không?

**Đáp án:** (1) Bốn phần, hai phần cuối là `""`. (2) Chuỗi toàn delimiter tạo toàn phần rỗng rồi bị xóa; chuỗi rỗng không chứa lần khớp `,` nào nên trả chính nó. (3) `split(",", -1)` và kiểm tra `length==4`. (4) Không, một trường chứa dấu cách, trường còn lại rỗng.

**Ghi nhớ:** **Giữ trường rỗng trước, kiểm tra schema sau.**