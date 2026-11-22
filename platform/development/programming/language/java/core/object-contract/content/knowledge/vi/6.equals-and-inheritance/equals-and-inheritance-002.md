# Thêm trường giá trị ở lớp con và nguy cơ mất tính bắc cầu của equals

## 1. Vấn đề: lớp con có thêm một phần của “giá trị”

Xét lớp cha **Point** lưu tọa độ x, y và định nghĩa hai điểm bằng nhau nếu chúng có cùng tọa độ. Sau đó ta kế thừa thành **ColoredPoint**, bổ sung trường **color**. Một câu hỏi thiết kế tưởng chừng đơn giản xuất hiện:

> **Point(1, 2)** có bằng **ColoredPoint(1, 2, "red")** không?

Nếu **có**, vì Point chỉ quan tâm tọa độ, thì một ColoredPoint màu đỏ và một ColoredPoint màu xanh có cùng tọa độ có thể đều bằng Point gốc. Nhưng nếu hai ColoredPoint phải xét thêm màu, chúng lại **không bằng nhau**. Khi đó quan hệ bằng nhau không còn bắc cầu.

Nếu **không**, lớp con cần đảm bảo **cả hai chiều** so sánh giữa Point và ColoredPoint đều trả về false. Nếu Point dùng **instanceof Point** trong equals mà ColoredPoint lại tự loại đối tượng Point, tính đối xứng sẽ bị phá vỡ.

Đây là xung đột giữa **kế thừa kiểu** (ColoredPoint là một Point) và **ngữ nghĩa bằng nhau theo giá trị** (ColoredPoint có thể có nhiều trường cấu thành giá trị hơn Point). Java cho phép override equals nhưng **không tự bảo đảm** hợp đồng equals khi cây kế thừa trở nên phức tạp.

### Phân biệt trường giá trị và trường chỉ phục vụ hiển thị

Không phải mọi trường mới đều cần tham gia equals.

- Nếu color chỉ là một thuộc tính trang trí, không ảnh hưởng định danh/giá trị logic, cả Point và ColoredPoint có thể tiếp tục so sánh theo x, y. Khi đó **hai ColoredPoint khác màu vẫn phải bằng nhau** theo quy tắc đã chọn.
- Nếu màu là thành phần của giá trị, thì hai ColoredPoint khác màu **phải khác nhau**. Khi đó không thể đồng thời cho mỗi ColoredPoint bằng Point cùng tọa độ và giữ một quan hệ equals hợp lệ.
- Nếu điều kiện bằng nhau đến từ khóa nghiệp vụ ổn định, chẳng hạn id, một trường mới như tên hiển thị có thể được bỏ qua có chủ đích. Quyết định này thuộc về **ngữ nghĩa miền dữ liệu**, không chỉ về cú pháp Java.

Bài này tập trung vào trường hợp **lớp con thực sự thêm một trường có ý nghĩa đối với phép so sánh giá trị**.

## 2. Hợp đồng Object.equals cần được giữ trong kế thừa

Đối với các tham chiếu khác null, equals phải thỏa năm yêu cầu chủ yếu:

| Tính chất | Phát biểu | Hệ quả khi phân nhóm/tìm kiếm |
| --- | --- | --- |
| **Phản xạ** | a.equals(a) == true | Một đối tượng luôn bằng chính nó |
| **Đối xứng** | a.equals(b) và b.equals(a) có cùng kết quả | Đổi thứ tự hai toán hạng không được đổi nghĩa |
| **Bắc cầu** | Nếu a.equals(b) và b.equals(c) đều true, thì a.equals(c) phải true | Không thể có a cùng nhóm b, b cùng nhóm c nhưng a khác nhóm c |
| **Nhất quán** | Kết quả lặp lại ổn định khi dữ liệu dùng để so sánh không đổi | Kết quả không dao động khi dùng trong cấu trúc dữ liệu |
| **So với null** | a.equals(null) == false | null không bằng đối tượng khác null |

**hashCode** có hợp đồng liên quan: **nếu a.equals(b) là true thì a.hashCode() phải bằng b.hashCode()**. Chiều ngược lại không bắt buộc đúng vì va chạm băm được phép xảy ra.

**Lưu ý:** hợp đồng **equals** mạnh hơn điều kiện “code chạy được” hoặc “các trường có vẻ được so sánh đúng”. Phương thức của từng lớp có thể nhìn hợp lý khi đọc riêng, nhưng sự kết hợp giữa lớp cha và lớp con vẫn vi phạm đối xứng hoặc bắc cầu.

### Hai lựa chọn dễ dẫn đến lỗi

Giả sử **Point.equals** so sánh x, y với mọi đối tượng **instanceof Point**.

1. **ColoredPoint chỉ nhận ColoredPoint:** Point.equals(red) trả true, nhưng red.equals(Point) trả false. Đây là lỗi **đối xứng**.
2. **ColoredPoint chấp nhận Point nhưng đòi màu khi gặp ColoredPoint:** Point.equals(red) và red.equals(Point) đều true. Đối xứng có thể được giữ, nhưng với hai màu khác nhau, **bắc cầu bị phá vỡ**.

Lỗi thứ hai khó thấy hơn vì các phép so sánh theo từng cặp Point–ColoredPoint đều có vẻ hợp lý.

## 3. Ví dụ Java 17: sửa đối xứng nhưng lại làm hỏng bắc cầu

Tạo file **BrokenEqualsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class BrokenEqualsDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color, "color");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point)) {
                return false;
            }
            if (!(obj instanceof ColoredPoint other)) {
                // Chấp nhận Point thường để cố giữ đối xứng.
                return super.equals(obj);
            }
            // Nếu cả hai đều có màu, lại dùng màu làm giá trị.
            return super.equals(obj) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Phải cùng hash với Point cùng tọa độ
            // vì hai đối tượng đó được xem là equals.
            return super.hashCode();
        }
    }

    public static void main(String[] args) {
        ColoredPoint red = new ColoredPoint(1, 2, "red");
        Point plain = new Point(1, 2);
        ColoredPoint blue = new ColoredPoint(1, 2, "blue");

        System.out.println("red == plain by equals: " + red.equals(plain));
        System.out.println("plain == blue by equals: " + plain.equals(blue));
        System.out.println("red == blue by equals: " + red.equals(blue));

        System.out.println("plain == red by equals: " + plain.equals(red));
        System.out.println("blue == plain by equals: " + blue.equals(plain));
        System.out.println("same hash: " +
            (red.hashCode() == plain.hashCode()));

        Set<Point> firstOrder = new HashSet<>();
        firstOrder.add(red);
        firstOrder.add(blue);
        firstOrder.add(plain);

        Set<Point> secondOrder = new HashSet<>();
        secondOrder.add(plain);
        secondOrder.add(red);
        secondOrder.add(blue);

        System.out.println("red, blue, plain -> size " + firstOrder.size());
        System.out.println("plain, red, blue -> size " + secondOrder.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac BrokenEqualsDemo.java
java BrokenEqualsDemo
~~~

Kết quả:

~~~text
red == plain by equals: true
plain == blue by equals: true
red == blue by equals: false
plain == red by equals: true
blue == plain by equals: true
same hash: true
red, blue, plain -> size 2
plain, red, blue -> size 1
~~~

### Phân tích chính xác lỗi

Chọn **a = red**, **b = plain**, **c = blue**:

~~~text
a.equals(b) == true
b.equals(c) == true
a.equals(c) == false
~~~

Hợp đồng đòi **a = b** và **b = c** kéo theo **a = c**, nhưng phương thức đã vi phạm. Ta có thể diễn đạt bằng các nhóm giả định:

~~~text
red   ── equals ── plain
blue  ── equals ── plain
red   ── NOT equals ── blue
~~~

Không tồn tại cách chia ba đối tượng này thành các nhóm tương đương hợp lệ mà vẫn giữ cả ba kết luận trên.

**Vì sao HashSet cho hai kích thước khác nhau?** Trong ví dụ, các đối tượng có cùng hash. Khi red và blue đến trước, cả hai được giữ vì chúng không bằng nhau; plain đến sau được coi bằng một phần tử đã có, nên còn hai phần tử. Khi plain đến trước, red và blue lần lượt được coi bằng plain, nên chỉ còn một. Thứ tự đưa phần tử vào đã làm biến đổi số lượng “giá trị duy nhất” theo cách trái với kỳ vọng của một quan hệ bằng nhau đúng.

Việc giữ **hashCode** giống nhau ở đây là cố ý để tuân điều kiện bắt buộc khi red.equals(plain) và blue.equals(plain) trả true. **Sửa hashCode để thêm color không giải quyết lỗi bắc cầu**; còn làm phát sinh vi phạm mới vì red bằng plain mà hash có thể khác.

> **Kết luận cho cách cài đặt này:** không thể có cả ba mong muốn “Point so bằng tọa độ”, “ColoredPoint so thêm màu” và “ColoredPoint vẫn bằng Point cùng tọa độ” mà vẫn giữ tính bắc cầu của equals.

## 4. Một lỗi khác: chỉ so sánh lớp con sẽ làm mất đối xứng

Nếu ColoredPoint override equals theo kiểu sau:

~~~java
@Override
public boolean equals(Object obj) {
    if (!(obj instanceof ColoredPoint other)) {
        return false;
    }
    return super.equals(obj) && color.equals(other.color);
}
~~~

Đây chỉ là **đoạn trích minh họa** đặt trong lớp ColoredPoint của phần trước, không phải chương trình độc lập.

Với Point.equals vẫn dùng **instanceof Point**:

- **plain.equals(red)** là true vì red cũng là Point và có cùng tọa độ.
- **red.equals(plain)** là false vì plain không phải ColoredPoint.

Đổi chiều so sánh cho kết quả khác nhau. Đó là vi phạm **đối xứng**. Kiểm tra bằng HashMap, HashSet hoặc thử vài trường hợp ngẫu nhiên có thể không phát hiện ngay; phải kiểm tra **cả hai chiều**.

## 5. Cách an toàn thứ nhất: cùng kiểu runtime mới bằng nhau

Nếu lớp con có thêm trường giá trị, một chính sách rõ ràng là: **Point và ColoredPoint không bao giờ bằng nhau**, kể cả khi tọa độ giống nhau. Trong từng kiểu cụ thể, tất cả trường giá trị được so sánh.

Trong trường hợp này, dùng **getClass()** để đòi **kiểu runtime chính xác** ở lớp cha và lớp con. Tạo file **ExactClassEqualsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ExactClassEqualsDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            Point other = (Point) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color, "color");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            if (!super.equals(obj)) {
                return false;
            }
            ColoredPoint other = (ColoredPoint) obj;
            return color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point red = new ColoredPoint(1, 2, "red");
        Point redAgain = new ColoredPoint(1, 2, "red");
        Point blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain equals red: " + plain.equals(red));
        System.out.println("red equals plain: " + red.equals(plain));
        System.out.println("red equals redAgain: " + red.equals(redAgain));
        System.out.println("red equals blue: " + red.equals(blue));
        System.out.println("matching hash: " +
            (red.hashCode() == redAgain.hashCode()));

        Set<Point> values = new HashSet<>();
        values.add(plain);
        values.add(red);
        values.add(redAgain);
        values.add(blue);
        System.out.println("unique values: " + values.size());
    }
}
~~~

Chạy:

~~~bash
javac ExactClassEqualsDemo.java
java ExactClassEqualsDemo
~~~

Kết quả:

~~~text
plain equals red: false
red equals plain: false
red equals redAgain: true
red equals blue: false
matching hash: true
unique values: 3
~~~

**Điểm cần hiểu rõ:**

- **getClass()** khiến cả hai chiều giữa Point và ColoredPoint trả false. Vì vậy không có “đối tượng trung gian” Point cùng tọa độ làm cầu nối giữa hai ColoredPoint khác màu.
- Khi hai đối tượng đều là ColoredPoint, **super.equals(obj)** vẫn kiểm tra tọa độ: lời gọi được thực hiện trên một instance ColoredPoint, nên kiểm tra **getClass()** trong lớp cha nhận cùng kiểu runtime ColoredPoint.
- **ColoredPoint.hashCode** bổ sung color đúng với các trường so sánh của ColoredPoint; nếu hai ColoredPoint bằng nhau thì tọa độ và màu giống nhau, nên chúng bắt buộc có hash giống nhau.
- **Point.hashCode** và **ColoredPoint.hashCode** vẫn có thể tình cờ trùng nhau. Điều này hợp lệ vì **hash bằng nhau không có nghĩa equals phải true**.
- **ColoredPoint** là **final** để không còn lớp cháu mới tự ý thêm trường giá trị hoặc override equals, giúp giới hạn nguy cơ.

**Đánh đổi:** Định nghĩa bằng nhau theo kiểu runtime chính xác không phù hợp nếu miền nghiệp vụ yêu cầu **đối tượng của hai kiểu khác nhau nhưng cùng ID phải được coi là một giá trị**. Nó cũng có thể gây bất ngờ với framework sinh proxy/subclass (ví dụ một số trường hợp ORM). Khi đó cần thiết kế chính sách bằng nhau theo ID hoặc khóa nghiệp vụ riêng, phù hợp vòng đời entity và cơ chế proxy; đừng đổi máy móc giữa **instanceof** và **getClass()**.

## 6. Cách an toàn thứ hai: ưu tiên composition để biểu diễn giá trị mở rộng

Khi đối tượng màu thực sự là **một loại giá trị khác**, có thể không cần thừa kế lớp Point. Hãy đặt Point làm một thành phần của ColoredPoint (composition). Hai lớp record Java tự cung cấp equals/hashCode cho toàn bộ thành phần giá trị của mỗi record.

Ví dụ đầy đủ **CompositionEqualsDemo.java**:

~~~java
public class CompositionEqualsDemo {
    record Point(int x, int y) {}

    record ColoredPoint(Point position, String color) {}

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(plain, "red");
        ColoredPoint redAgain = new ColoredPoint(new Point(1, 2), "red");
        ColoredPoint blue = new ColoredPoint(new Point(1, 2), "blue");

        System.out.println("plain equals red: " + plain.equals(red));
        System.out.println("red equals redAgain: " + red.equals(redAgain));
        System.out.println("red equals blue: " + red.equals(blue));
        System.out.println("same position: " +
            red.position().equals(blue.position()));
    }
}
~~~

Chạy:

~~~bash
javac CompositionEqualsDemo.java
java CompositionEqualsDemo
~~~

Kết quả:

~~~text
plain equals red: false
red equals redAgain: true
red equals blue: false
same position: true
~~~

Ở đây **red** và **blue** cùng **position** nhưng khác **giá trị ColoredPoint**. Hai khái niệm được tách rõ, không phải cố làm cho equals của cả cây kế thừa vừa bỏ qua vừa xét màu.

Khi cần kiểm tra hai vật thể có cùng vị trí hay không, gọi **red.position().equals(blue.position())**. Khi cần xem cả vị trí lẫn màu là giá trị, gọi **red.equals(blue)**. Đây là hai phép so sánh với **hai mục đích** khác nhau.

**Record không tự làm mọi trường bên trong bất biến sâu.** Nếu component là danh sách, mảng hay object có thể thay đổi, nội dung bên trong vẫn có thể bị thay đổi hoặc có ngữ nghĩa equals không như mong đợi. Trong ví dụ, **Point** là record chứa hai int và color là String bất biến, nên khóa giá trị đơn giản và ổn định.

## 7. Một số chiến lược thiết kế khác và giới hạn của chúng

### 7.1. Khóa logic chung được coi là định danh duy nhất

Giả sử cả lớp cha và lớp con đại diện cho **cùng thực thể nghiệp vụ**, có khóa **id** không đổi, còn trường bổ sung chỉ là dữ liệu mô tả. Khi ấy có thể chọn **equals chỉ dựa vào id** cho mọi đối tượng cùng miền định danh (với xử lý kiểu phù hợp).

Tuy nhiên, lúc đó hai instance có cùng id nhưng khác color **vẫn phải bằng nhau** theo hợp đồng đã chọn. Không thể vừa tuyên bố **color là một phần của giá trị equals ở lớp con**, vừa bỏ qua nó khi so với lớp cha.

Một phương án thiết kế là thực thi equals/hashCode **final** tại lớp cha cho khóa định danh chung, hoặc dùng khóa riêng. Việc gắn **final** vào equals chỉ ngăn override; bản thân chính sách ID vẫn phải đúng với nghiệp vụ, phân biệt namespace/tenant và vòng đời ID.

### 7.2. Mẫu canEqual

Một số thiết kế lớp có chủ đích cho phép kế thừa equals dùng mẫu **canEqual**, trong đó lớp cha yêu cầu đối tượng còn lại công nhận khả năng so sánh qua một phương thức hai chiều, và lớp con từ chối so bằng lớp cha khi nó thêm trường giá trị.

Ý tưởng cơ bản là cả hai phía phải đồng ý **có cùng loại giá trị có thể so sánh**, trước khi xét từng trường. Mẫu này có thể giữ hợp đồng cho một phân cấp được kiểm soát chặt chẽ, nhưng đòi hỏi **mọi lớp con** tuân cùng quy ước và cài đặt đúng equals/hashCode. Không nên thêm canEqual như bản vá cục bộ vào một cây kế thừa vốn đã có nhiều override không nhất quán.

### 7.3. Phương thức so sánh theo mục đích khác nhau

Nếu vừa cần **cùng vị trí** vừa cần **cùng vị trí và màu**, có thể cung cấp phương thức như **samePosition(Point)** hoặc dùng comparator/key extractor riêng. Những phương thức này có thể trả về kết quả khác equals mà không gây mâu thuẫn vì **chúng không cùng tuyên bố là hợp đồng Object.equals**.

Ví dụ, hai ColoredPoint khác màu có thể trả true khi so **samePosition**, nhưng false khi so **equals**. Khi lưu vào HashSet, chỉ equals/hashCode quyết định khái niệm giá trị duy nhất của tập.

### 7.4. Tránh kế thừa giá trị khi không cần thiết

**final class** hoặc **record** giúp ngăn lớp con mở rộng trạng thái bằng nhau; composition dùng được khi cần kiểu giá trị giàu thông tin hơn. Đây thường là lựa chọn đơn giản hơn so với phải duy trì hợp đồng equals qua nhiều tầng kế thừa.

## 8. Các lỗi thường gặp khi sửa equals

**Chỉ đổi instanceof sang getClass ở lớp con.** Nếu lớp cha vẫn chấp nhận lớp con, thì vẫn có thể xuất hiện:

~~~text
parent.equals(child) == true
child.equals(parent) == false
~~~

Cần thống nhất quy tắc ở **toàn bộ các lớp liên quan**, không sửa từng bên độc lập.

**Để color tham gia hashCode trong khi vẫn chấp nhận Point thường là equals.** Khi ColoredPoint.equals(Point) là true mà hash lại tính thêm color, có thể vi phạm trực tiếp hợp đồng hashCode. Cách đúng là thay đổi **định nghĩa equals** trước rồi đồng bộ hashCode.

**Cho phép một lớp con thêm trường nhưng không cập nhật equals/hashCode.** Nếu color thật sự là giá trị mà không được so sánh, hai đối tượng khác màu vẫn bị xem là bằng nhau. Đó là lỗi ngữ nghĩa nghiệp vụ; ngay cả khi quan hệ còn phản xạ, đối xứng và bắc cầu, kết quả vẫn có thể không đúng yêu cầu.

**Dùng trường mutable để tính hashCode.** Nếu tọa độ, id hoặc color thay đổi sau khi đối tượng đã làm khóa HashMap/HashSet, phép tìm lại có thể sai. Ưu tiên thành phần khóa bất biến và không sửa trạng thái có ảnh hưởng tới equals/hashCode khi đang dùng làm khóa.

**Cho rằng cùng hash là cùng giá trị.** Hai đối tượng không bằng nhau có thể cùng hash. HashMap/HashSet dựa cả vào hashCode và equals; hash không thay thế equals.

**Bỏ qua null, proxy và việc gọi qua tham chiếu lớp cha.** Equals nhận **Object**, có thể được gọi từ nhiều nguồn khác nhau. Kiểm thử phải bao gồm các đối tượng ở các lớp khác nhau trong phân cấp, trường hợp null và mọi kiểu subclass thực sự xuất hiện trong ứng dụng.

## 9. Checklist kiểm thử hồi quy cho lớp cha và lớp con

Dựng tập mẫu gồm:

- **p1, p2:** hai đối tượng lớp cha cùng giá trị; **p3:** lớp cha khác giá trị.
- **c1, c2:** hai đối tượng lớp con có cùng toàn bộ trường giá trị.
- **c3:** lớp con chỉ khác trường mới, ví dụ color.
- **c4:** lớp con khác tọa độ/trường kế thừa.
- Mọi cặp cha–con có cùng dữ liệu lớp cha nhưng khác kiểu runtime; thêm null.

Sau đó kiểm tra:

1. **Phản xạ và null:** mọi a đều a.equals(a) == true và a.equals(null) == false.
2. **Đối xứng:** với mỗi cặp a, b, kiểm tra **a.equals(b) == b.equals(a)**. Đặc biệt đổi thứ tự cha–con.
3. **Bắc cầu:** với mọi bộ a, b, c mà **a.equals(b)** và **b.equals(c)** true, kiểm tra **a.equals(c)** true; đặc biệt thử **con A → cha → con B khác trường mới**.
4. **Hash tương thích:** hễ a.equals(b) true thì **a.hashCode() == b.hashCode()**.
5. **Tính nhất quán:** gọi lặp lại trong khi không thay đổi dữ liệu phải cùng kết quả.
6. **HashSet/HashMap:** thêm các phần tử theo nhiều thứ tự khác nhau; số giá trị logic riêng biệt và khả năng tra cứu phải phù hợp với định nghĩa equals.
7. **Subclasses khác nhau:** nếu có nhiều lớp con cùng kế thừa một lớp cha, thử cả các cặp giữa hai lớp con; chỉ thử một lớp con là chưa đủ.

Có thể triển khai các kiểm tra đối xứng/bắc cầu thành vòng lặp trên các mẫu có sẵn hoặc dùng thư viện kiểm tra equals/hashCode mà dự án đang sử dụng. Đối với test dùng Java **assert**, phải chạy JVM với cờ **-ea** thì assertion mới được thực thi; test framework thường cung cấp assertion riêng.

### Câu hỏi tự đánh giá

1. Vì sao **red.equals(plain)** và **plain.equals(blue)** đều true nhưng **red.equals(blue)** false là lỗi hợp đồng, dù mỗi phương thức nhìn riêng có vẻ hợp lý?
2. Vì sao thêm **color** vào hashCode không khắc phục tình huống trên?
3. Khi nào bạn muốn **Point** khác **ColoredPoint** ngay cả khi x, y giống nhau?
4. Nếu color chỉ là thông tin hiển thị, equals và hashCode nên xét những trường nào?
5. Nếu nghiệp vụ vừa cần “cùng vị trí” vừa cần “cùng vị trí và màu”, vì sao nên dùng **hai phép so sánh có tên rõ nghĩa** hoặc **hai kiểu giá trị**?

## 10. Hướng dẫn lựa chọn thiết kế

| Ý nghĩa nghiệp vụ | Thiết kế phù hợp | Hợp đồng cần giữ |
| --- | --- | --- |
| Lớp con thêm trường **thực sự thuộc giá trị equals** | So bằng **getClass** nhất quán qua phân cấp, hoặc dùng **composition/record** | Không cho cha và con tương đương chỉ vì phần dữ liệu chung khớp |
| Cả cha và con đại diện cùng thực thể, trường mới chỉ mô tả | Có thể dùng **định danh logic bất biến**, với equals/hashCode nhất quán | Trường mới không được lúc xét lúc bỏ trong equals |
| Cần nhiều tiêu chí so sánh cùng lúc | Viết **phương thức có tên**, **key extractor** hoặc loại giá trị riêng | Không ép các tiêu chí mâu thuẫn vào một equals |
| Cây kế thừa mở, nhiều lớp con override | Xem lại kiến trúc; cân nhắc **canEqual** hoặc bỏ kế thừa giá trị | Mọi lớp trong cây phải giữ phản xạ, đối xứng, bắc cầu và hashCode |

**Ghi nhớ cốt lõi:** Khi lớp con bổ sung **trường giá trị**, lỗi dễ thấy là **mất đối xứng** do hai lớp chấp nhận nhau khác nhau. Cố sửa bằng cách cho lớp con chấp nhận cả lớp cha có thể tạo lỗi sâu hơn là **mất bắc cầu** giữa hai lớp con khác giá trị, với lớp cha làm trung gian. Muốn equals đáng tin, hãy thiết kế **một định nghĩa bằng nhau nhất quán cho mọi kiểu liên quan**; khi trường bổ sung tạo ra một giá trị khác, **tách kiểu giá trị hoặc từ chối so bằng giữa các lớp** là cách rõ ràng.
