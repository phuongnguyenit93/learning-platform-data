# Lớp trừu tượng vừa `abstract` vừa `sealed` hoặc `non-sealed`

Trong Java, `abstract` và `sealed` / `non-sealed` giải quyết hai vấn đề khác nhau. `abstract` quy định lớp có thể được khởi tạo trực tiếp hay không và liệu lớp có thể để lại phương thức chưa triển khai; `sealed` kiểm soát những lớp nào được phép kế thừa trực tiếp; `non-sealed` mở lại nhánh kế thừa vốn nằm dưới một kiểu `sealed`. Vì vậy, một lớp có thể vừa `abstract` vừa `sealed`, hoặc vừa `abstract` vừa `non-sealed`.

Các ví dụ trong bài sử dụng Java 17 trở lên, là phiên bản mà sealed classes được chuẩn hóa.

## 1. Ý nghĩa của từng modifier

- **`abstract`:** không thể dùng `new` để tạo trực tiếp đối tượng từ lớp đó. Lớp có thể khai báo phương thức abstract và để lớp con triển khai. Một lớp abstract vẫn có thể có trường, constructor, phương thức có thân và logic dùng chung.
- **`sealed`:** giới hạn các lớp con trực tiếp vào danh sách được cho phép. Danh sách này thường được viết bằng mệnh đề `permits`. Mỗi lớp con được phép phải khai báo một trong các modifier `final`, `sealed` hoặc `non-sealed`.
- **`non-sealed`:** áp dụng cho một lớp con trực tiếp của kiểu `sealed` để cho phép nhánh đó tiếp tục được mở rộng mà không cần liệt kê trước mọi hậu duệ.
- **`final`:** không cho phép lớp có lớp con. Một lớp `final` không thể đồng thời là `abstract` vì hai mục đích mâu thuẫn nhau.

Các modifier này không thay thế lẫn nhau. `abstract` không tự giới hạn cây kế thừa; `sealed` không tự làm lớp thành abstract; `non-sealed` không bắt buộc lớp phải là concrete.

## 2. Kết hợp `abstract sealed`

Khai báo `abstract sealed class Shape permits Circle, Group { ... }` có nghĩa là:

1. Không thể khởi tạo trực tiếp `Shape`.
2. `Shape` có thể chứa phương thức abstract mà các lớp con concrete phải thực hiện.
3. Chỉ những kiểu được liệt kê trong `permits` mới được kế thừa trực tiếp từ `Shape`.
4. Mỗi lớp con trực tiếp phải quyết định nhánh kế thừa của nó bằng `final`, `sealed` hoặc `non-sealed`.

Lớp `abstract sealed` phù hợp khi muốn mô hình hóa một khái niệm nền tảng chưa hoàn chỉnh, đồng thời muốn kiểm soát các kiểu trực tiếp được phép xuất hiện trong hệ thống. Ví dụ, một lớp biểu thức có thể định nghĩa hợp đồng `evaluate()` nhưng chỉ cho phép một số nhánh biểu thức đã biết.

## 3. Kết hợp `abstract non-sealed`

Một khai báo như `abstract non-sealed class PluginNode extends Node { ... }` có nghĩa là lớp này vẫn không thể được khởi tạo trực tiếp và có thể để lại phương thức abstract, nhưng nhánh kế thừa từ nó được mở. Các lớp khác có thể kế thừa `PluginNode` mà không cần được liệt kê trong `permits` của lớp gốc `Node`.

Điều kiện quan trọng: `non-sealed` chỉ hợp lệ khi lớp trực tiếp mở rộng một lớp `sealed` hoặc triển khai một interface `sealed`. Không thể thêm `non-sealed` tùy ý vào một lớp không nằm dưới kiểu sealed.

## 4. Ví dụ hoàn chỉnh: một cây lớp có cả ba loại nhánh

Chương trình sau cho thấy một lớp gốc `abstract sealed`, một nhánh `abstract sealed` tiếp tục giới hạn lớp con, một nhánh `abstract non-sealed` cho phép mở rộng tự do, và một lớp concrete `final`.

Lưu toàn bộ mã trong `Main.java`:

```java
abstract sealed class Node
        permits NumberNode, GroupNode, ExtensionNode {
    abstract int value();
}

final class NumberNode extends Node {
    private final int number;

    NumberNode(int number) {
        this.number = number;
    }

    @Override
    int value() {
        return number;
    }
}

abstract sealed class GroupNode extends Node
        permits PairNode {
    // Có thể giữ lại phương thức abstract value()
    // để lớp con concrete hoàn thành.
}

final class PairNode extends GroupNode {
    private final Node left;
    private final Node right;

    PairNode(Node left, Node right) {
        this.left = left;
        this.right = right;
    }

    @Override
    int value() {
        return left.value() + right.value();
    }
}

abstract non-sealed class ExtensionNode extends Node {
    // Nhánh này được mở cho các lớp con tùy ý.
}

final class CustomNode extends ExtensionNode {
    private final int number;

    CustomNode(int number) {
        this.number = number;
    }

    @Override
    int value() {
        return number;
    }
}

public class Main {
    public static void main(String[] args) {
        Node number = new NumberNode(3);
        Node pair = new PairNode(
                new NumberNode(4),
                new NumberNode(5));
        Node custom = new CustomNode(10);

        System.out.println(number.value());
        System.out.println(pair.value());
        System.out.println(custom.value());
    }
}
```

Biên dịch và chạy:

```text
javac Main.java
java Main
```

Kết quả chuẩn:

```text
3
9
10
```

Trong ví dụ này:

- `Node` là `abstract sealed`: không thể khởi tạo trực tiếp, có hợp đồng `value()`, và chỉ cho phép ba lớp con trực tiếp đã liệt kê.
- `NumberNode` là `final`, nên nhánh này kết thúc.
- `GroupNode` là `abstract sealed`, nên nó được phép trì hoãn việc triển khai `value()` và tiếp tục kiểm soát lớp con thông qua `permits PairNode`.
- `PairNode` là `final` và triển khai `value()`.
- `ExtensionNode` là `abstract non-sealed`: nó vẫn có thể để lại phương thức abstract, nhưng cho phép những lớp như `CustomNode` tiếp tục kế thừa.
- `CustomNode` triển khai `value()` nên có thể được khởi tạo.

## 5. Quy tắc biên dịch cần nhớ

**Quy tắc của `sealed`:**

- Mọi lớp con trực tiếp của một lớp sealed phải thuộc danh sách được phép.
- Lớp con được phép phải trực tiếp kế thừa lớp sealed đó và phải khai báo `final`, `sealed` hoặc `non-sealed`.
- Các kiểu được phép phải đáp ứng quy tắc module/package của Java: trong cùng named module, hoặc cùng package khi dùng unnamed module.
- `permits` nêu các lớp con trực tiếp, không liệt kê toàn bộ hậu duệ. Ví dụ, `Node` liệt kê `ExtensionNode`, còn `CustomNode` là hậu duệ nằm dưới nhánh `non-sealed`.
- Nếu các lớp con được khai báo cùng compilation unit, Java có quy tắc suy ra danh sách permitted trong trường hợp phù hợp; viết `permits` tường minh thường dễ đọc hơn khi học.

**Quy tắc của `abstract`:**

- Không được khởi tạo trực tiếp lớp abstract bằng `new`.
- Lớp abstract có thể giữ các phương thức abstract chưa triển khai. Một lớp con cũng là abstract có thể tiếp tục trì hoãn; lớp concrete phải triển khai đầy đủ các phương thức abstract còn lại.
- Constructor của lớp abstract vẫn chạy khi một lớp con được khởi tạo. Lớp abstract có thể chứa trạng thái và phương thức dùng chung.
- `abstract` không buộc lớp con phải là abstract. Một lớp con `final` hoặc concrete `non-sealed` vẫn hợp lệ nếu nó triển khai đầy đủ hợp đồng.

## 6. Những tổ hợp hợp lệ và không hợp lệ

| Khai báo | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `abstract sealed class A permits B {}` | Có, nếu `B` là lớp con trực tiếp hợp lệ | Không khởi tạo `A`; giới hạn lớp con trực tiếp |
| `abstract non-sealed class B extends A {}` | Có, nếu `A` là sealed | Không khởi tạo `B`; mở rộng nhánh kế thừa |
| `sealed class A permits B {}` | Có, nếu khai báo các lớp con đúng quy tắc | Lớp có thể concrete hoặc abstract |
| `abstract final class A {}` | Không | Abstract cần có khả năng được kế thừa để hoàn thiện, còn final cấm kế thừa |
| `non-sealed class B {}` khi không có sealed parent | Không | `non-sealed` chỉ mở một nhánh xuất phát từ kiểu sealed |
| `sealed non-sealed class A {}` | Không | Hai modifier điều khiển trạng thái sealed đối nghịch nhau |

## 7. Chọn tổ hợp nào trong thiết kế?

Dùng `abstract sealed` khi lớp đại diện cho một khái niệm chưa hoàn chỉnh và bạn cần kiểm soát rõ các loại lớp có thể kế thừa trực tiếp. Cách này hữu ích trong mô hình miền nghiệp vụ, cây cú pháp, biểu thức, thông điệp hoặc các loại sự kiện có tập biến thể được kiểm soát.

Dùng `abstract non-sealed` khi một nhánh cần giữ hợp đồng abstract và hành vi chung, nhưng muốn cho module khác hoặc mã mở rộng tự định nghĩa thêm lớp con. Hãy cân nhắc ranh giới API: mở nhánh `non-sealed` đồng nghĩa với việc mã sử dụng không thể giả định rằng toàn bộ hậu duệ của nhánh đó đã được liệt kê.

Nếu không cần kiểm soát tập lớp con, một lớp abstract thông thường thường đơn giản hơn. Nếu cần một tập phân cấp đóng, hãy dùng `sealed` và quyết định từng nhánh nên kết thúc bằng `final`, tiếp tục kiểm soát bằng `sealed`, hay mở bằng `non-sealed`.

Khi đọc một khai báo như `abstract sealed` hoặc `abstract non-sealed`, hãy trả lời hai câu hỏi riêng: **lớp có thể được khởi tạo trực tiếp và đã triển khai đầy đủ hành vi chưa?** (`abstract`) và **ai được phép kế thừa lớp này hoặc tiếp tục mở rộng nhánh?** (`sealed` / `non-sealed`). Hai câu trả lời kết hợp sẽ xác định đúng vai trò của lớp trong hệ phân cấp.
