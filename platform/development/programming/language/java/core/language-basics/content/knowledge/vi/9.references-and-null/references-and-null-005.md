# Thay đổi trạng thái khác với gán lại biến tham chiếu trong Java

> **Java core — language-basics / Tham chiếu và null**  
> **Yêu cầu:** JDK 17 trở lên; chỉ sử dụng Java standard library.  
> **Mục tiêu:** Phân biệt **sửa trạng thái đối tượng** (*mutation*) với **gán lại một biến tham chiếu** (*reassignment*); dự đoán chính xác tác động qua alias, tham số phương thức, `final`, mảng và `String`.

## 1. Hai thao tác, hai đối tượng tác động khác nhau

Xét một lớp có trạng thái thay đổi được:

~~~java
class Meter {
    int value;
    Meter(int value) { this.value = value; }
}
~~~

Sau đó:

~~~java
Meter first = new Meter(10);
Meter second = first;

second.value = 15;       // Mutation: sửa object đang được cả hai biến tham chiếu.
second = new Meter(7);   // Reassignment: chỉ đổi tham chiếu lưu trong second.
~~~

- **Mutation:** `second.value = 15` thay đổi trường `value` của **object Meter hiện có**. Khi `first` và `second` còn trỏ cùng object, đọc `first.value` thấy **15**.
- **Reassignment:** `second = new Meter(7)` tạo object mới rồi thay **giá trị tham chiếu của biến `second`**. Biến `first` vẫn trỏ object cũ có `value = 15`.
- **Phép gán `second = first`** tự nó chỉ sao chép giá trị tham chiếu, **không tạo bản sao object**.

Trước thao tác gán lại:

~~~text
first  ─┐
        ├──> Meter(value = 15)
second ─┘
~~~

Sau `second = new Meter(7)`:

~~~text
first  ────> Meter(value = 15)
second ────> Meter(value = 7)
~~~

**Điểm mấu chốt:** Mutation đổi **dữ liệu bên trong object**; reassignment đổi **object mà một biến tham chiếu đang trỏ tới**. Một thao tác không tự động làm thao tác còn lại xảy ra.

## 2. Bảng dự đoán hành vi

Giả sử khởi đầu với `Meter a = new Meter(10); Meter b = a;`:

| Câu lệnh tiếp theo | `a.value` | `b.value` / liên hệ | Giải thích |
| --- | ---: | --- | --- |
| `b.value = 12;` | 12 | 12; `a == b` là true | Cùng object bị sửa |
| `b = new Meter(20);` | 12 | 20; `a == b` là false | Chỉ b nhận tham chiếu mới |
| `b.value = 25;` | 12 | 25 | Sửa object mới của b |
| `b = a;` | 12 | 12; `a == b` là true | b trỏ lại object cũ |
| `b = null;` | 12 | b là null | Chỉ b không còn trỏ tới object |

Các hàng này được thực hiện **theo thứ tự** từ trên xuống. `a == b` là phép so sánh **identity tham chiếu**, không phải kiểm tra hai object có dữ liệu giống nhau hay không.

Gán `b = null` cũng **không hủy object**: nếu `a` còn tham chiếu, object vẫn có thể được dùng. Đừng coi `null` là lệnh giải phóng bộ nhớ ngay lập tức.

## 3. Chương trình Java 17+ chạy độc lập

Tạo tệp **MutationVsReassignmentDemo.java**:

~~~java
public final class MutationVsReassignmentDemo {
    private static final class Meter {
        private int value;

        Meter(int value) {
            this.value = value;
        }

        void increase(int amount) {
            value += amount;
        }

        int value() {
            return value;
        }
    }

    private static void mutate(Meter meter) {
        meter.increase(3);
    }

    private static void redirect(Meter meter) {
        meter = new Meter(99);
        System.out.println("insideRedirect=" + meter.value());
    }

    public static void main(String[] args) {
        Meter original = new Meter(10);
        Meter alias = original;

        System.out.println("initialSame=" + (original == alias));
        alias.increase(5);
        System.out.println("afterMutation=" + original.value());

        mutate(original);
        System.out.println("afterMethodMutation=" + alias.value());

        redirect(original);
        System.out.println("afterMethodRedirect=" + original.value());

        alias = new Meter(7);
        System.out.println("sameAfterReassign=" + (original == alias));
        System.out.println("original=" + original.value());
        System.out.println("alias=" + alias.value());

        alias = null;
        System.out.println("aliasNull=" + (alias == null));
        System.out.println("originalStill=" + original.value());

        final Meter fixed = original;
        fixed.increase(2);
        System.out.println("finalObjectValue=" + original.value());

        int[] firstArray = {1, 2};
        int[] secondArray = firstArray;
        secondArray[0] = 9;
        System.out.println("sharedArray=" + firstArray[0]);
        secondArray = new int[] {4, 5};
        System.out.println("afterArrayReassign=" + firstArray[0]
                + "," + secondArray[0]);

        String text1 = "Hi";
        String text2 = text1;
        text2 = text2.concat("!");
        System.out.println("strings=" + text1 + "," + text2);
    }
}
~~~

Biên dịch/chạy tại thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 MutationVsReassignmentDemo.java
java MutationVsReassignmentDemo
~~~

**Expected output chính xác:**

~~~text
initialSame=true
afterMutation=15
afterMethodMutation=18
insideRedirect=99
afterMethodRedirect=18
sameAfterReassign=false
original=18
alias=7
aliasNull=true
originalStill=18
finalObjectValue=20
sharedArray=9
afterArrayReassign=9,4
strings=Hi,Hi!
~~~

Đọc từng mốc:

1. `alias = original` cho hai biến cùng trỏ Meter 10, nên `initialSame=true`.
2. `alias.increase(5)` sửa object chung thành 15; `mutate(original)` sửa tiếp thành 18. Cả hai biến đều nhìn thấy.
3. `redirect(original)` nhận **bản sao giá trị tham chiếu** qua tham số. Dòng `meter = new Meter(99)` chỉ thay biến **meter** bên trong phương thức; khi quay về, `original.value()` vẫn là 18.
4. `alias = new Meter(7)` đổi object mà alias trỏ đến. `original` không đổi, nên `sameAfterReassign=false`.
5. `alias = null` chỉ bỏ tham chiếu của alias; `original` vẫn đọc được 18.
6. `fixed` là tham chiếu `final` trỏ tới cùng object của `original`. Phép `fixed.increase(2)` được phép nên giá trị object tăng thành 20.
7. Mảng cũng là object: sửa `secondArray[0]` làm `firstArray[0]` thành 9. Nhưng gán `secondArray = new int[] {...}` chỉ đổi biến secondArray; phần tử của firstArray vẫn 9.
8. `String` là immutable: `concat` không sửa chuỗi `"Hi"`. Biến `text2` được gán tham chiếu tới chuỗi kết quả `"Hi!"`; `text1` vẫn cho `"Hi"`.


## 4. Ranh giới giữa method sửa tại chỗ và trả object mới

Một method nhận `Meter` nhận **bản sao giá trị tham chiếu**. Gọi `meter.increase(3)` trong method sẽ sửa object được chia sẻ; gán `meter = new Meter(99)` chỉ đổi biến tham số. Nếu cần tạo một phiên bản độc lập, method có thể trả về `new Meter(old.value() + 1)` và bên gọi tự quyết định `original = nextMeter(original)`. Giao diện method nên làm rõ nó **mutate** đầu vào hay **trả object mới**.


## 5. `final` khóa biến, không khóa object

`final Meter meter = new Meter(1);` cho phép `meter.increase(1)` nếu API hỗ trợ, nhưng không cho phép `meter = new Meter(2)`. Cùng logic, `final int[] numbers = {1, 2};` vẫn cho phép `numbers[0] = 9`. Muốn dữ liệu không bị sửa bởi alias khác, phải dựa vào thiết kế bất biến, quyền truy cập và cách API công bố trạng thái; chỉ viết `final` ở biến là chưa đủ.


## 6. Thiết kế API theo chủ đích thay đổi trạng thái

Một API kiểu `void increase(Meter meter)` thể hiện thao tác sửa trạng thái đang chia sẻ; API kiểu `Meter increased(Meter old)` có thể tạo và trả về giá trị mới để caller chọn có gán lại biến hay không. Với đối tượng mutable, tài liệu API nên nói rõ liệu đầu vào có bị sửa và kết quả có chia sẻ tham chiếu với dữ liệu cũ.

Nếu không muốn người ngoài sửa trạng thái nội bộ, cân nhắc bản sao bảo vệ (*defensive copy*) hoặc kiểu bất biến. Sao chép một mảng tham chiếu bằng `clone()` tạo mảng mới nhưng vẫn có thể chia sẻ các phần tử object mutable, vì vậy phải xét cấu trúc dữ liệu trước khi chọn cách copy.

## 7. Lỗi hay gặp và bài tập

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`b = a` sao chép cả object.” | Sai: chỉ sao chép **giá trị tham chiếu** |
| “Sửa qua b chỉ ảnh hưởng b.” | Sai nếu a và b cùng tham chiếu object mutable |
| “`b = new Meter(...)` làm a đổi luôn.” | Sai: chỉ biến b nhận tham chiếu mới |
| “Method gán `param = new ...` sẽ đổi biến bên gọi.” | Sai: Java truyền tham số theo giá trị |
| “`b = null` xóa object.” | Sai: chỉ đổi biến b; alias khác còn dùng object |
| “`final` cấm mọi thay đổi object.” | Sai: `final` cấm gán lại biến, không cấm mutation |
| “`String.concat` sửa String cũ.” | Sai: `String` bất biến; kết quả là giá trị chuỗi mới/có thể được tái dùng tùy API |

**Bài tập 1.** Khởi tạo `Meter a = new Meter(3); Meter b = a;`, rồi gọi `b.increase(2)`. Dự đoán `a.value()` và `a == b`.

**Bài tập 2.** Sau bài 1, thực hiện `b = new Meter(10);` và `b.increase(1)`. Những thao tác nào ảnh hưởng a, những thao tác nào chỉ ảnh hưởng b?

**Bài tập 3.** Truyền a vào `changeValue` và `changeVariable`. Thử dự đoán trước khi chạy: object của a có đổi không? Biến a có trỏ object khác không?

**Bài tập 4.** Với `final int[] nums = {1, 2};`, hãy thử `nums[1] = 7;` và `nums = new int[]{3, 4};`. Dòng nào hợp lệ, vì sao?

**Bài tập 5.** Viết `String a = "X"; String b = a; b += "Y";` rồi in a và b. Tại sao đây là **gán lại tham chiếu tới kết quả** chứ không phải sửa object String?

### Tổng kết

**Mutation** đổi trạng thái của object đang tồn tại và có thể quan sát qua **mọi alias** tới object ấy. **Reassignment** đổi tham chiếu được lưu trong **một biến**, không tự sửa object cũ hoặc gán lại các biến khác. Khi đọc mã Java, luôn hỏi: **“Dòng này sửa object hay đổi biến đang trỏ object?”** — đó là chìa khóa để dự đoán đúng hành vi.
