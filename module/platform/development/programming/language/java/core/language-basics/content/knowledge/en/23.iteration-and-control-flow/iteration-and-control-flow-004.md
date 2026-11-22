# Thay đổi đối tượng được tham chiếu qua biến vòng lặp trong Java

> **Java core — language-basics / Duyệt và chuyển luồng**  
> **Môi trường:** JDK 17+, một file Java, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Phân biệt **thay đổi trạng thái đối tượng** qua biến enhanced `for` và **gán lại biến vòng lặp**; biết cách thay phần tử thực sự của mảng/`List`, hiểu alias, kiểu bất biến và những rủi ro khi sửa collection lúc đang duyệt.

## 1. Enhanced `for` nhận giá trị phần tử vào biến cục bộ

~~~java
for (ElementType element : source) {
    // Sử dụng element.
}
~~~

Với mảng hoặc `Iterable`, mỗi lượt lấy một phần tử rồi gán giá trị đó cho biến cục bộ `element`. Cần phân biệt:

- **Kiểu nguyên thủy** như `int`: biến chứa **bản sao giá trị**. Sửa biến không sửa phần tử nguồn.
- **Kiểu tham chiếu** như `StringBuilder`, `Box`: biến chứa **bản sao giá trị tham chiếu** tới cùng đối tượng. Gọi phương thức sửa đối tượng có thể quan sát được qua mảng/list.
- **Gán lại biến** bằng `element = otherObject` chỉ thay **biến cục bộ** của lượt đó; không tự thay tham chiếu lưu ở mảng/list.

Đây là ngữ nghĩa gán và tham chiếu của Java, không phải cơ chế “truyền tham chiếu” cho biến. Enhanced `for` **không cung cấp một vị trí có thể ghi ngược vào collection**.

## 2. Sửa trạng thái đối tượng: phần tử gốc vẫn trỏ cùng đối tượng

Ví dụ với lớp `Box` có trạng thái mutable:

~~~java
static final class Box {
    private int value;

    Box(int value) { this.value = value; }

    void add(int amount) { value += amount; }

    int value() { return value; }

    @Override
    public String toString() { return "Box(" + value + ")"; }
}
~~~

Một mảng chứa các tham chiếu `Box`:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box.add(10); // Thay đổi đối tượng mà phần tử trỏ tới.
}
// boxes chứa Box(11), Box(12).
~~~

Trong mỗi lượt, `box` và `boxes[index]` **cùng trỏ đến một đối tượng**. Do đó thay đổi thuộc tính qua `box.add(10)` được nhìn thấy khi truy cập mảng về sau. Cơ chế tương tự áp dụng cho `ArrayList<Box>` và các nguồn `Iterable<Box>` có cùng tham chiếu đối tượng.

Đối tượng được thay đổi, nhưng **vị trí phần tử trong mảng/list không bị thay thế**: không có thao tác `boxes[index] = ...` hoặc `list.set(index, ...)` trong ví dụ.

## 3. Gán lại biến vòng lặp không thay phần tử nguồn

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box = new Box(99); // Chỉ gán cho biến local box.
}
// Mảng vẫn chứa Box(1), Box(2).
~~~

Việc gán lại có thể làm `box` trỏ tới đối tượng khác **trong phần còn lại của lượt**, nhưng tham chiếu lưu ở mảng không thay đổi. Sang lượt tiếp theo, biến vòng lặp lại nhận phần tử tiếp theo từ mảng.

Thậm chí nếu kết hợp hai thao tác:

~~~java
for (Box box : boxes) {
    box.add(1);        // Sửa Box ban đầu trong mảng.
    box = new Box(99); // Đổi biến local, mảng không nhận Box(99).
}
~~~

Sau vòng này, phần tử mảng là `Box(2)` và `Box(3)`, **không phải** `Box(99)`.

Nếu khai báo `for (final Box box : boxes)`, Java cấm gán lại `box`, nhưng vẫn cho gọi `box.add(1)` nếu đối tượng cho phép sửa trạng thái: `final` bảo vệ **giá trị tham chiếu của biến**, không làm đối tượng tự động bất biến.

## 4. Muốn thay phần tử thật, dùng chỉ số hoặc `ListIterator.set`

Với **mảng**, thay tham chiếu bằng phép gán theo chỉ số:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (int i = 0; i < boxes.length; i++) {
    boxes[i] = new Box(boxes[i].value() * 2);
}
// boxes: Box(2), Box(4).
~~~

Với `List` hỗ trợ cập nhật, dùng `list.set(index, value)` khi có chỉ số. Khi muốn duyệt và thay phần tử tại vị trí hiện hành mà không tự quản lý chỉ số, `ListIterator.set(value)` là cách phù hợp:

~~~java
java.util.List<Box> list = new java.util.ArrayList<>();
list.add(new Box(3));
list.add(new Box(4));

java.util.ListIterator<Box> it = list.listIterator();
while (it.hasNext()) {
    Box old = it.next();
    it.set(new Box(old.value() * 2));
}
// list: [Box(6), Box(8)].
~~~

| Thao tác | Thay đối tượng đang được tham chiếu? | Thay phần tử ở mảng/list? |
| --- | --- | --- |
| `box.add(5)` | Có, nếu `Box` mutable | Không thay tham chiếu phần tử |
| `box = new Box(5)` | Không sửa đối tượng cũ | Không |
| `array[i] = new Box(5)` | Không sửa đối tượng cũ | Có |
| `list.set(i, new Box(5))` | Không sửa đối tượng cũ | Có nếu list cho phép |
| `listIterator.set(new Box(5))` | Không sửa đối tượng cũ | Có nếu iterator cho phép |

`List.of(...)` không hỗ trợ thay phần tử bằng `set`; cần dùng `ArrayList` hoặc một cấu trúc cho phép sửa. Tuy vậy, một list không sửa được cấu trúc vẫn có thể **chứa đối tượng mutable**: hạn chế thay phần tử và hạn chế sửa trạng thái đối tượng là hai vấn đề khác nhau.

## 5. Alias: nhiều biến cùng tham chiếu, nhưng thay phần tử không đổi alias cũ

Giả sử hai biến cùng giữ một đối tượng:

~~~java
Box original = new Box(5);
Box alias = original;
alias.add(2);
// original.value() == 7; alias.value() == 7.
~~~

Đây là **aliasing**: thay đổi trạng thái qua một tham chiếu được quan sát qua tham chiếu còn lại.

Nhưng nếu list chứa `original` và ta **thay phần tử** bằng một đối tượng mới, `alias` vẫn trỏ tới `original`:

~~~java
java.util.List<Box> list =
        new java.util.ArrayList<>(java.util.List.of(original));

list.set(0, new Box(100));
// alias.value() == 7, list.get(0).value() == 100.
// alias == list.get(0) là false.
~~~

Do đó, cần quyết định nghiệp vụ đang muốn **điều chỉnh đối tượng chung** hay **thay một phần tử bằng đối tượng khác**. Sửa đối tượng được nhiều nơi tham chiếu có thể ảnh hưởng không chủ ý tới tất cả nơi đang giữ alias.

## 6. Đối tượng bất biến: ví dụ `String`

`String` là kiểu **bất biến** (*immutable*): không có phương thức thay nội dung của chính đối tượng. Phương thức `toUpperCase()` tạo/trả về một giá trị chuỗi thích hợp mà không sửa chuỗi nguồn.

~~~java
java.util.List<String> names = new java.util.ArrayList<>(
        java.util.List.of("an", "binh"));

for (String name : names) {
    name = name.toUpperCase(java.util.Locale.ROOT);
}
// names vẫn là [an, binh].
~~~

Ở đây gán lại biến `name` không thay phần tử list. Để chuyển đổi chính các phần tử nguồn:

~~~java
for (int i = 0; i < names.size(); i++) {
    names.set(i, names.get(i).toUpperCase(java.util.Locale.ROOT));
}
// names là [AN, BINH].
~~~

Ngược lại, `StringBuilder` mutable, nên `builder.append("!")` trong enhanced `for` thay đổi nội dung đối tượng:

~~~java
java.util.List<StringBuilder> builders = new java.util.ArrayList<>();
builders.add(new StringBuilder("A"));

for (StringBuilder builder : builders) {
    builder.append("!");
}
// builders chứa StringBuilder có nội dung "A!".
~~~

**Quy tắc:** “Kiểu tham chiếu” không đồng nghĩa “đối tượng có thể sửa”. Cần xem API của kiểu và tính bất biến của đối tượng.

## 7. Null và sửa cấu trúc collection trong lúc duyệt

- Nếu phần tử là `null`, biến enhanced `for` cũng nhận null. Gọi `box.add(1)` khi `box == null` sẽ ném `NullPointerException`; phải kiểm tra trước.
- Nếu **mảng hoặc Iterable nguồn** là null, vòng enhanced `for` không thể bắt đầu duyệt và thường ném `NullPointerException`.
- Khi duyệt `ArrayList` bằng enhanced `for`, tránh `list.add(...)` / `list.remove(...)` trực tiếp trong thân vì đó là **thay đổi cấu trúc** ngoài iterator, có thể gây `ConcurrentModificationException`. Đừng dựa vào fail-fast như một cơ chế đồng bộ chắc chắn.
- Nếu cần xóa lúc duyệt, dùng `Iterator.remove()` nếu iterator hỗ trợ; nếu cần thay phần tử hiện hành, dùng `ListIterator.set()` nếu list/iterator hỗ trợ.
- Thay **trạng thái bên trong Box** khi đang duyệt `List<Box>` không phải tự động là sửa cấu trúc `List`. Tuy nhiên, các cấu trúc dựa trên thuộc tính để sắp xếp/hash có thể mất tính nhất quán nếu đổi thuộc tính ảnh hưởng khóa sau khi chèn.

Ví dụ xử lý phần tử nullable:

~~~java
Box[] values = {null, new Box(5)};

for (Box box : values) {
    if (box != null) {
        box.add(1);
    }
}
// values chứa null và Box(6).
~~~

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **LoopReferenceMutationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public final class LoopReferenceMutationDemo {
    static final class Box {
        private int value;

        Box(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }

        void add(int amount) {
            value += amount;
        }

        @Override
        public String toString() {
            return "Box(" + value + ")";
        }
    }

    public static void main(String[] args) {
        Box[] array = {new Box(1), new Box(2)};
        for (Box box : array) {
            box.add(10);
        }
        System.out.println("arrayMutation=" + Arrays.toString(array));

        for (Box box : array) {
            box = new Box(99);
        }
        System.out.println("arrayRebind=" + Arrays.toString(array));

        for (int i = 0; i < array.length; i++) {
            array[i] = new Box(array[i].value() * 2);
        }
        System.out.println("arrayReplace=" + Arrays.toString(array));

        List<Box> list = new ArrayList<>(
                List.of(new Box(3), new Box(4)));
        for (Box box : list) {
            box.add(5);
        }
        System.out.println("listMutation=" + list);

        for (Box box : list) {
            box = new Box(0);
        }
        System.out.println("listRebind=" + list);

        ListIterator<Box> it = list.listIterator();
        while (it.hasNext()) {
            Box old = it.next();
            it.set(new Box(old.value() + 1));
        }
        System.out.println("listReplace=" + list);

        Box alias = list.get(0);
        alias.add(100);
        System.out.println("aliasMutation=" + list);

        list.set(0, new Box(1));
        System.out.println("listAfterSet=" + list);
        System.out.println("aliasOld=" + alias);
        System.out.println("aliasSame=" + (alias == list.get(0)));

        List<String> names = new ArrayList<>(List.of("an", "binh"));
        for (String name : names) {
            name = name.toUpperCase(Locale.ROOT);
        }
        System.out.println("stringsRebind=" + names);

        for (int i = 0; i < names.size(); i++) {
            names.set(i, names.get(i).toUpperCase(Locale.ROOT));
        }
        System.out.println("stringsReplace=" + names);

        List<StringBuilder> builders = new ArrayList<>();
        builders.add(new StringBuilder("A"));
        for (StringBuilder builder : builders) {
            builder.append("!");
        }
        System.out.println("builderMutation=" + builders);

        Box[] nullable = {null, new Box(5)};
        for (Box box : nullable) {
            if (box != null) {
                box.add(1);
            }
        }
        System.out.println("nullable=" + Arrays.toString(nullable));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell, Command Prompt):

~~~bash
javac -encoding UTF-8 LoopReferenceMutationDemo.java
java LoopReferenceMutationDemo
~~~

**Expected stdout chính xác:**

~~~text
arrayMutation=[Box(11), Box(12)]
arrayRebind=[Box(11), Box(12)]
arrayReplace=[Box(22), Box(24)]
listMutation=[Box(8), Box(9)]
listRebind=[Box(8), Box(9)]
listReplace=[Box(9), Box(10)]
aliasMutation=[Box(109), Box(10)]
listAfterSet=[Box(1), Box(10)]
aliasOld=Box(109)
aliasSame=false
stringsRebind=[an, binh]
stringsReplace=[AN, BINH]
builderMutation=[A!]
nullable=[null, Box(6)]
~~~

So sánh `arrayMutation`/`arrayRebind` và `listMutation`/`listRebind` để thấy **sửa trạng thái đối tượng ≠ gán lại biến**. `listAfterSet` khác `aliasOld` chứng minh thay phần tử không làm mọi tham chiếu cũ tự động đổi sang đối tượng mới.

## 9. Lỗi thường gặp và bài tập

| Lỗi | Cách sửa |
| --- | --- |
| Cho rằng `box = new Box(...)` trong for-each thay mảng/list | Dùng `array[i] = ...` hoặc `list.set(i, ...)` |
| Cho rằng `box.add(1)` chỉ sửa bản sao đối tượng | Phân biệt bản sao **tham chiếu** với đối tượng gốc dùng chung |
| Dùng `String.toUpperCase()` rồi bỏ kết quả | Gán kết quả vào phần tử theo chỉ số nếu muốn thay nội dung list |
| Nghĩ `final Box box` làm `Box` bất biến | `final` chỉ ngăn gán lại biến tham chiếu |
| Gọi phương thức trên phần tử null | Guard `if (box != null)` |
| Xóa/thêm trực tiếp vào `ArrayList` trong enhanced for | Dùng iterator hỗ trợ xóa, hoặc chuyển cách xử lý |
| Sửa phần tử của `List.of(...)` bằng `set` | Dùng một list cho phép sửa như `ArrayList` |

**Bài 1.** Cho `Box[] array = {new Box(2), new Box(4)}`. Dự đoán kết quả nếu mỗi lượt lần lượt chạy `box.add(3)` và `box = new Box(0)`. Giải thích riêng hai phép.

**Bài 2.** Dùng vòng `for` có chỉ số để thay tất cả phần tử mảng bằng `new Box(old.value() * 2)`. So sánh với sửa đối tượng đang tồn tại bằng `add`.

**Bài 3.** Viết `ArrayList<String>` có hai chuỗi thường, chuyển thành chữ hoa bằng `set` và kiểm tra vì sao gán lại biến trong for-each không đủ.

**Bài 4.** Giữ một alias tới phần tử đầu của `List<Box>`, sau đó thay phần tử bằng `set(0, new Box(...))`. Alias cũ và phần tử mới còn là cùng đối tượng không?

**Bài 5.** Viết đoạn xử lý `List<Box>` có phần tử null; thêm một guard để tránh `NullPointerException` khi thay đổi thuộc tính.

### Ghi nhớ

**Enhanced for chỉ đưa giá trị phần tử vào biến cục bộ.** Với kiểu tham chiếu, giá trị ấy trỏ tới cùng đối tượng: **gọi phương thức mutable** có thể sửa trạng thái đối tượng chung, còn **gán lại biến vòng lặp** không thay phần tử gốc. Muốn thay phần tử, dùng chỉ số, `List.set` hoặc `ListIterator.set`; nhớ phân biệt mutable/immutable và lưu ý alias, null, cũng như các giới hạn khi sửa collection trong lúc duyệt.
