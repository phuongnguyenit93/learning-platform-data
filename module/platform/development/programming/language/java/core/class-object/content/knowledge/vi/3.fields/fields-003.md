# Trường đối tượng và dữ liệu riêng của từng thể hiện trong Java

Một lớp có thể tạo ra nhiều đối tượng, và mỗi đối tượng mang **trạng thái riêng**. Trong Java, thành phần trực tiếp lưu trạng thái đó là **trường đối tượng** (*instance field*, còn gọi là trường không `static`). Hiểu rõ điều này giúp trả lời các câu hỏi: vì sao sửa điểm của học viên A không đổi điểm của học viên B, vì sao hai biến vẫn có thể thấy cùng một thay đổi, và điều gì xảy ra nếu trường chứa tham chiếu đến một đối tượng dùng chung.

## 1. Trường đối tượng là gì?

**Field** là biến được khai báo trong thân lớp, bên ngoài constructor, phương thức hoặc khối lệnh. **Instance field** là trường **không khai báo `static`**. Mỗi đối tượng được tạo ra từ lớp có phần trạng thái tương ứng với các instance field được khai báo hoặc thừa kế theo quy tắc ngôn ngữ Java.

Ví dụ một phần lớp (chưa phải chương trình chạy độc lập):

~~~java
class ScoreCard {
    String playerName; // instance field
    int score;         // instance field
}
~~~

Mỗi `new ScoreCard()` tạo một đối tượng mới với **giá trị các trường riêng**. Một đối tượng có thể có `score = 10`, còn đối tượng khác có `score = 0`.

Điều này không có nghĩa JVM nhất thiết phải sắp xếp các trường theo một bố cục bộ nhớ cụ thể mà chương trình có thể truy cập trực tiếp. Java quy định **ngữ nghĩa trạng thái của từng đối tượng**; chi tiết lưu trữ do JVM thực hiện.

### Ba khái niệm cần phân biệt

| Khái niệm | Ví dụ | Điều được tạo hoặc lưu |
| --- | --- | --- |
| Lớp | `class ScoreCard { ... }` | Định nghĩa kiểu, những trường và hành vi hợp lệ |
| Đối tượng | `new ScoreCard()` | Một instance có trạng thái riêng |
| Biến tham chiếu | `ScoreCard a` | Một biến có thể trỏ đến đối tượng hoặc chứa `null` |

Câu lệnh `ScoreCard a;` trong một phương thức **chưa tạo đối tượng**. Câu lệnh `a = new ScoreCard();` mới tạo một instance và gán tham chiếu của nó cho biến `a`. Giá trị được lưu trong biến `a` khác với các giá trị trường nằm trong đối tượng mà nó tham chiếu đến.

## 2. Một lớp, nhiều bản trạng thái độc lập

Tạo tệp **`InstanceFieldDemo.java`** và dùng Java 17 trở lên:

~~~java
class ScoreCard {
    private final String playerName;
    private int score;

    ScoreCard(String playerName) {
        if (playerName == null || playerName.isBlank()) {
            throw new IllegalArgumentException("Tên người chơi không hợp lệ");
        }
        this.playerName = playerName;
        this.score = 0;
    }

    void earn(int points) {
        if (points <= 0) {
            throw new IllegalArgumentException("Điểm cộng phải dương");
        }
        score = Math.addExact(score, points);
    }

    int score() {
        return score;
    }

    String display() {
        return playerName + ": " + score;
    }
}

public class InstanceFieldDemo {
    public static void main(String[] args) {
        ScoreCard an = new ScoreCard("An");
        ScoreCard binh = new ScoreCard("Binh");

        an.earn(10);
        binh.earn(5);
        an.earn(3);

        System.out.println(an.display());
        System.out.println(binh.display());

        ScoreCard aliasOfAn = an;
        aliasOfAn.earn(2);
        System.out.println(an.display());

        ScoreCard anotherAn = new ScoreCard("An");
        System.out.println(anotherAn.display());
        System.out.println(an == aliasOfAn);
        System.out.println(an == anotherAn);
    }
}
~~~

Đứng tại thư mục chứa tệp và chạy:

~~~bash
javac -encoding UTF-8 InstanceFieldDemo.java
java InstanceFieldDemo
~~~

Kết quả stdout:

~~~text
An: 13
Binh: 5
An: 15
An: 0
true
false
~~~

Chương trình có một định nghĩa lớp `ScoreCard`, nhưng **ba đối tượng** được tạo bằng ba lần `new ScoreCard(...)`: `an`, `binh` và `anotherAn` trỏ tới ba instance khác nhau.

- `an.earn(10)` rồi `an.earn(3)` làm điểm của đối tượng An từ 0 thành 13; điểm của Bình vẫn là 5.
- `aliasOfAn = an` chỉ **sao chép tham chiếu** đến đối tượng An. Không có lệnh `new` nên không tạo đối tượng thứ tư.
- `aliasOfAn.earn(2)` tác động đến chính đối tượng mà `an` cũng tham chiếu; bởi vậy `an.display()` in `An: 15`.
- `anotherAn = new ScoreCard("An")` tạo **đối tượng mới**. Trùng tên người chơi không khiến hai đối tượng dùng chung trường `score`; điểm của `anotherAn` vẫn là 0.
- `an == aliasOfAn` là `true`, vì hai tham chiếu cùng trỏ đến một object. `an == anotherAn` là `false`, vì đó là hai object khác nhau.

### Sơ đồ trạng thái sau các thao tác

~~~text
Định nghĩa lớp ScoreCard
  - playerName: String
  - score: int
  - earn(...), display(), score()
             |
             | tạo nhiều instance
             v

biến an -----------+----> Đối tượng #1: ScoreCard
biến aliasOfAn -----+       playerName = "An"
                            score      = 15

biến binh --------------> Đối tượng #2: ScoreCard
                            playerName = "Binh"
                            score      = 5

biến anotherAn ---------> Đối tượng #3: ScoreCard
                            playerName = "An"
                            score      = 0
~~~

**Kết luận cốt lõi từ ví dụ:** sự độc lập phụ thuộc vào **số đối tượng thực sự được tạo**, không phụ thuộc số biến tham chiếu hay việc các đối tượng có dữ liệu ban đầu giống nhau.

## 3. `this` chọn trường của đúng đối tượng hiện tại

Trong constructor:

~~~java
this.playerName = playerName;
this.score = 0;
~~~

`this` là tham chiếu đến đối tượng hiện tại đang được khởi tạo hoặc đang thực thi phương thức instance. Ở câu lệnh đầu, `this.playerName` là field của đối tượng; `playerName` ở bên phải là **tham số** của constructor.

Khi gọi:

~~~java
an.earn(10);
binh.earn(5);
~~~

Java thực hiện phương thức `earn` với **đối tượng nhận lời gọi** khác nhau. Bên trong `earn`, tên `score` được hiểu là trường của `this` trong ngữ cảnh đó, tương đương cách viết `this.score`.

Không phải mỗi object có một bản sao mã máy/phần thân phương thức `earn` độc lập theo nghĩa ngôn ngữ. **Phần khai báo hành vi ở lớp được tái sử dụng; trạng thái instance mà hành vi thao tác là riêng của đối tượng nhận.**

### Tên trùng giữa field, parameter và local variable

Xem đoạn minh họa:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void setValue(int value) {
        this.value = value;
    }

    int value() {
        return this.value;
    }
}
~~~

Đây là **định nghĩa lớp độc lập, không có `main`**. Trong constructor và `setValue`, tham số `value` **che tên** instance field cùng tên. Viết `this.value` giúp chỉ rõ trường của object, còn `value` không có `this` chỉ tham số. Nếu viết `value = value;`, cả hai vế đều là tham số và **không cập nhật trường**.

Khi không có biến gần hơn cùng tên, như trong `ScoreCard.earn`, có thể viết ngắn `score` thay cho `this.score`. Từ khóa `this` **không dùng được trong ngữ cảnh `static`**.

## 4. Mỗi lần khởi tạo đối tượng tạo một bản trạng thái riêng

Với `new ScoreCard("An")` trong ví dụ chính, các instance fields được đặt ở giá trị mặc định **cho chính instance đó** trước khi field initializers và constructor hoàn tất. `int score` bắt đầu ở `0`, còn reference field như `String playerName` mặc định `null` trước khi constructor gán tên bắt buộc. Nếu tạo tiếp `new ScoreCard("Binh")`, đối tượng sau không tái sử dụng `score` hoặc `playerName` của đối tượng trước.

Thứ tự tổng quát cần nhớ là: **giá trị mặc định → khởi tạo phần superclass phù hợp → instance field/initializer blocks theo thứ tự nguồn trong lớp → constructor body của lớp**; `this(...)` chaining có quy tắc riêng và không chạy lặp lại initializer của cùng lớp chỉ vì một constructor ủy quyền. Đây là thứ tự khái niệm, không phải lời khẳng định về bố cục heap vật lý.

Một field `final` như `private final String playerName;` vẫn **thuộc riêng từng đối tượng**. Nó phải được gán theo definite-assignment rules trong quá trình xây dựng hợp lệ, thường qua constructor, rồi không được gán lại; `final` không biến toàn bộ đối tượng thành bất biến. Phần trọng tâm ở đây là **hai lần tạo instance cho hai trạng thái riêng**, chứ không lặp lại phép thử mọi giá trị mặc định hay phân tích các nhánh definite assignment của biến cục bộ.

## 5. Instance field khác static field

**Instance field:** mỗi đối tượng chứa trạng thái riêng.  
**Static field:** thành viên thuộc lớp, được sử dụng chung bởi các instance của cùng lớp trong cùng ngữ cảnh nạp lớp.

Ví dụ đoạn minh họa:

~~~java
class VisitCounter {
    static int totalVisits; // thuộc lớp
    int myVisits;           // riêng từng đối tượng

    void visit() {
        myVisits++;
        totalVisits++;
    }
}
~~~

Nếu có hai instance `first` và `second`, gọi `first.visit()` hai lần và `second.visit()` một lần trong luồng tuần tự thì:

| Trường được đọc | Giá trị |
| --- | ---: |
| `first.myVisits` | 2 |
| `second.myVisits` | 1 |
| `VisitCounter.totalVisits` | 3 |

Ví dụ `VisitCounter` chỉ là **định nghĩa lớp để minh họa**, không có `main`. Biến `myVisits` phải là instance field vì mỗi đối tượng cần đếm lượt riêng; biến `totalVisits` được cố ý thiết kế để đếm chung ở cấp lớp.

**Nhầm lẫn nguy hiểm:** nếu vô tình đặt `static` vào trường cần riêng cho từng đối tượng, chẳng hạn `static int score`, mọi `ScoreCard` sẽ dùng chung một trường điểm thay vì có điểm riêng.

Mặt khác, dùng `static` không làm phép `++` trở thành an toàn khi có nhiều luồng cập nhật. Cả việc truy cập instance field và static field đều phải xem xét vấn đề đồng thời nếu cùng trạng thái bị nhiều luồng chia sẻ.

## 6. “Mỗi trường riêng” không đồng nghĩa mọi dữ liệu tham chiếu đều độc lập

Với kiểu nguyên thủy như `int`, trường lưu trực tiếp **giá trị**. Với kiểu tham chiếu như `StringBuilder`, trường lưu **tham chiếu** đến object khác. Hai đối tượng chủ có thể có **hai trường tham chiếu riêng** nhưng giá trị của hai trường cùng trỏ đến **một đối tượng được chia sẻ**.

Tạo tệp **`ReferenceFieldDemo.java`**:

~~~java
import java.util.Objects;

class Notebook {
    private StringBuilder content;

    Notebook(StringBuilder content) {
        this.content = Objects.requireNonNull(content);
    }

    void append(String text) {
        content.append(text);
    }

    void replaceBuffer(StringBuilder replacement) {
        content = Objects.requireNonNull(replacement);
    }

    String text() {
        return content.toString();
    }
}

public class ReferenceFieldDemo {
    public static void main(String[] args) {
        StringBuilder shared = new StringBuilder("A");
        Notebook first = new Notebook(shared);
        Notebook second = new Notebook(shared);

        first.append("B");
        System.out.println(first.text());
        System.out.println(second.text());

        second.replaceBuffer(new StringBuilder("C"));
        System.out.println(first.text());
        System.out.println(second.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceFieldDemo.java
java ReferenceFieldDemo
~~~

Stdout:

~~~text
AB
AB
AB
C
~~~

Điều gì đã xảy ra?

1. `new Notebook(shared)` được gọi hai lần nên có hai đối tượng `Notebook`, mỗi object sở hữu một field `content` riêng.
2. **Ban đầu**, hai field này chứa cùng một giá trị tham chiếu đến đối tượng `StringBuilder` được tạo ở dòng `shared`.
3. `first.append("B")` làm thay đổi `StringBuilder` được chia sẻ; do đó `second.text()` cũng trả về `AB`.
4. `second.replaceBuffer(new StringBuilder("C"))` chỉ gán lại **trường content của object second**. Trường `content` của `first` vẫn trỏ đến builder cũ và trả `AB`; object `second` trả `C`.

Sơ đồ trước bước `replaceBuffer`:

~~~text
first  ---> Notebook #1 ---> content ----+
                                         |
                                         +--> StringBuilder "AB"
                                         |
second ---> Notebook #2 ---> content ----+
~~~

Sơ đồ sau bước `replaceBuffer`:

~~~text
first  ---> Notebook #1 ---> content ----> StringBuilder "AB"

second ---> Notebook #2 ---> content ----> StringBuilder "C"
~~~

Điều này giải thích một vấn đề thực tế: nếu constructor nhận `List`, `Map`, mảng hay một đối tượng mutable rồi **lưu thẳng tham chiếu** vào field, bên gọi và các instance khác có thể vẫn giữ tham chiếu tới dữ liệu đó. Nếu thiết kế yêu cầu **quyền sở hữu độc lập**, cần cân nhắc tạo bản sao phù hợp hoặc dùng kiểu bất biến; bản sao nông có thể vẫn chia sẻ các đối tượng con.

Ví dụ `String` là kiểu tham chiếu nhưng **bất biến** theo API, nên chia sẻ cùng một `String` không tạo ra tình huống sửa nội dung tại chỗ như `StringBuilder`. Không nên suy ra “mọi field kiểu tham chiếu đều nguy hiểm”; hãy xét **tính khả biến và cách chia sẻ tham chiếu**.

## 7. Đọc, ghi trường và nguyên tắc đóng gói

Nếu các field của `ScoreCard` là `public`, mã bên ngoài có thể thực hiện `an.score = -999;` và phá vỡ yêu cầu điểm không âm. Thiết kế trong ví dụ chính dùng:

~~~java
private int score;

void earn(int points) {
    if (points <= 0) {
        throw new IllegalArgumentException("Điểm cộng phải dương");
    }
    score = Math.addExact(score, points);
}

int score() {
    return score;
}
~~~

*Các dòng này trích từ bên trong lớp `ScoreCard`, không phải một tệp biên dịch riêng.*

- `private` giới hạn truy cập trực tiếp tới trường `score` ở phạm vi lớp khai báo.
- `earn` là điểm vào được kiểm soát để thay đổi trạng thái; đầu vào không hợp lệ bị từ chối **trước** khi gán.
- `Math.addExact` tránh tràn số nguyên một cách âm thầm; nếu cộng tràn, phép gán không được thực hiện.
- `score()` cung cấp giá trị quan sát hiện tại mà không cung cấp một field có thể tùy ý sửa.

**Getter không phải nghĩa vụ bắt buộc cho mọi trường.** Chỉ cung cấp phương thức đọc hay cập nhật khi nó thực sự phục vụ hành vi người dùng của lớp. Trong thiết kế hướng đối tượng, hành vi có ý nghĩa nghiệp vụ thường rõ ràng hơn việc để mọi nơi trực tiếp chỉnh sửa từng field.

`private` không phải ranh giới bảo mật cho một dịch vụ triển khai thực tế; nó là cơ chế truy cập ở cấp ngôn ngữ để hỗ trợ kiểm soát tính đúng đắn và đóng gói.

## 8. Tham chiếu, phép gán và tham số phương thức

Sự độc lập của instance fields thường bị hiểu nhầm khi sử dụng phép gán.

| Câu lệnh | Có tạo object mới? | Hệ quả |
| --- | --- | --- |
| `ScoreCard a = new ScoreCard("An");` | Có | `a` trỏ tới một object mới |
| `ScoreCard b = a;` | Không | `a`, `b` cùng trỏ tới object đó |
| `ScoreCard c = new ScoreCard("An");` | Có | `c` trỏ tới object khác, dù dữ liệu ban đầu giống |
| `b = c;` | Không | Biến `b` đổi tham chiếu; object cũ không bị sửa chỉ vì gán |
| `a = null;` | Không | Biến `a` thôi tham chiếu; object có thể vẫn được biến khác giữ |

Trong Java, **mọi đối số đều truyền theo giá trị**. Với biến tham chiếu, giá trị được truyền là **bản sao tham chiếu**. Vì vậy phương thức nhận tham chiếu có thể thay đổi instance fields của object được chia sẻ nếu có quyền, nhưng phép gán lại chính tham số không làm thay đổi biến của bên gọi.

Ví dụ ngắn (đặt trong lớp đã có `ScoreCard`; đoạn minh họa **không độc lập**):

~~~java
static void award(ScoreCard card) {
    card.earn(1);                 // đổi state của object được trỏ đến
    card = new ScoreCard("Khac"); // chỉ đổi biến tham số cục bộ
}
~~~

Nếu `award(an)` hoàn thành, object mà `an` trỏ đến được cộng 1 điểm; `an` không tự chuyển sang object có tên `"Khac"`.

Đừng suy ra từ việc hai **biến tham chiếu khác nhau** rằng hai **đối tượng** cũng khác nhau. Và đừng suy ra từ việc hai **đối tượng khác nhau** rằng chúng không thể chia sẻ **đối tượng con** qua field kiểu tham chiếu.

## 9. Vòng đời field và giới hạn của ví dụ

Instance field tồn tại như một phần trạng thái của **đối tượng**. Phạm vi của biến dùng tham chiếu và thời gian đối tượng còn được truy cập là hai vấn đề khác nhau:

- Một biến cục bộ `ScoreCard card` hết phạm vi không đồng nghĩa object bị xóa ngay. Đối tượng có thể còn được tham chiếu từ biến khác, field của object khác hoặc nơi khác.
- Đối tượng không còn có thể truy cập được có thể trở thành ứng viên thu hồi của garbage collector. **Không có bảo đảm** nó được thu hồi ngay sau phép gán `null`.
- Đối với object có một field tham chiếu chứa `null`, field đó vẫn **tồn tại**; chỉ là nó chưa trỏ đến đối tượng nào.
- Cùng một định nghĩa lớp có thể được dùng để tạo không, một hoặc nhiều đối tượng; chỉ đối tượng thực sự được tạo mới có các giá trị instance field cụ thể.

### Một ghi chú về đa luồng

Các ví dụ trên thực hiện tuần tự. “Trường riêng của từng object” **không có nghĩa** luôn an toàn trong chương trình đa luồng. Nếu hai luồng cùng có tham chiếu đến **một** `ScoreCard`, chúng có thể cùng đọc/ghi **một** field `score`. Phép cập nhật `score = Math.addExact(score, points)` không phải thao tác nguyên tử trên toàn bộ chuỗi đọc–tính–ghi. Với đồng thời, phải thiết kế cơ chế đồng bộ, atomic hoặc sở hữu trạng thái phù hợp.

Ngược lại, khi mỗi luồng sở hữu một object riêng và không chia sẻ tham chiếu đến trạng thái mutable khác, sự độc lập của instance fields giúp tránh tác động qua lại giữa chúng.

## 10. Các lỗi và cách nhận biết

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Có hai biến nên chắc chắn có hai instance” | `ScoreCard b = a;` không gọi `new` | Hai biến có thể tham chiếu cùng object |
| “Hai object cùng tên nên dùng chung score” | Tên nghiệp vụ và danh tính object là hai thứ khác nhau | Mỗi instance có field `score` riêng |
| “Đặt `static` cho score vẫn giữ điểm riêng” | Static field được dùng chung ở cấp lớp | Dùng instance field cho dữ liệu riêng |
| “Field `final` làm object bất biến” | Các field khác hoặc object tham chiếu vẫn có thể thay đổi | `final` chỉ hạn chế gán lại chính field |
| “Field tham chiếu riêng thì nội dung chắc chắn riêng” | Hai field có thể cùng trỏ tới object mutable | Xem xét aliasing, sao chép và bất biến |
| “Field và local variable đều mặc định bằng 0” | Local variable phải được gán chắc chắn trước khi đọc | Quy tắc mặc định áp dụng cho field và phần tử mảng |
| “Dùng biến `a` hết scope là object biến mất ngay” | Object có thể vẫn có đường tham chiếu khác | GC quyết định khi nào thu hồi object không còn truy cập |
| “Field instance tự an toàn khi nhiều luồng dùng” | Nhiều luồng có thể cùng giữ tham chiếu đến một object | Cần đồng bộ nếu cùng sửa shared mutable state |

Khi quan sát lỗi dữ liệu “tự thay đổi” giữa hai chỗ trong chương trình, hãy kiểm tra: có phải hai biến đang cùng trỏ đến một object? Field được khai báo `static` hay instance? Nếu field là tham chiếu, liệu hai object có đang giữ cùng một đối tượng con không?

## 11. Bài tập tự kiểm tra

**Bài 1 — Tách trạng thái.** Với:

~~~java
ScoreCard a = new ScoreCard("A");
ScoreCard b = new ScoreCard("B");
a.earn(4);
b.earn(2);
~~~

`a.score()` và `b.score()` là bao nhiêu? Tại sao thay đổi của A không thay đổi B?

**Bài 2 — Sao chép tham chiếu.** Sau bài 1, viết:

~~~java
ScoreCard c = a;
c.earn(1);
~~~

`a.score()` và `c.score()` là bao nhiêu? Đã có bao nhiêu đối tượng `ScoreCard` được tạo?

**Bài 3 — Tạo đối tượng mới cùng dữ liệu.** Viết `ScoreCard d = new ScoreCard("A");`. Điểm của `d` có bằng điểm của `a` không? `a == d` là `true` hay `false`?

**Bài 4 — Tham chiếu trong field.** Hai `Notebook` được tạo với cùng một `StringBuilder`. Nếu một notebook `append` dữ liệu, notebook kia đọc được phần mới không? Nếu notebook thứ hai được gán một `StringBuilder` mới qua `replaceBuffer`, điều gì còn được chia sẻ?

**Bài 5 — Thiết kế trường.** Trong lớp `ShoppingBasket`, nên khai báo `itemCount` là instance field hay `static` nếu mỗi giỏ hàng cần có số món riêng? Khi nào một biến cấp lớp mới có ý nghĩa?

**Đáp án tham khảo:**

1. `a.score() == 4`, `b.score() == 2`; hai instance khác nhau có hai field `score` riêng.
2. Cả hai là 5; `c` chỉ alias `a`, tổng số instance vẫn là 2.
3. `d.score() == 0` và `a == d` là `false`: lệnh `new` thứ ba tạo object mới.
4. Ban đầu có vì cùng trỏ đến builder mutable; sau khi thay tham chiếu ở notebook thứ hai, hai field trỏ đến hai builder khác nhau.
5. Dùng instance field cho `itemCount` của từng giỏ; chỉ dùng static khi chủ ý lưu trạng thái thuộc về lớp, được chia sẻ giữa các giỏ.

Điểm cần ghi nhớ là **mỗi object sở hữu giá trị instance field của nó, nhưng tham chiếu tới object có thể được chia sẻ**. Muốn biết một thay đổi tác động tới đâu, hãy xác định đối tượng nhận thao tác và lần theo các tham chiếu bên trong các field.
