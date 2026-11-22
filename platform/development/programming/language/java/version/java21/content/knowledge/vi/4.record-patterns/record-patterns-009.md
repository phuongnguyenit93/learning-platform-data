# Phạm vi, tên biến và điều kiện sử dụng biến sau matching

## Mục tiêu

Record Patterns trong Java 21 cho phép kiểm tra kiểu của một record và lấy các component của nó ngay trong cùng một pattern. Khi pattern khớp, các biến được khai báo trong pattern có thể được sử dụng ở phần mã mà trình biên dịch xác định chắc chắn là đã xảy ra matching.

Điểm cần nắm vững là **phạm vi của pattern variable phụ thuộc vào luồng điều khiển**. Biến không tự động tồn tại ở toàn bộ method hoặc sau câu lệnh `if`; nó chỉ được dùng tại những vị trí mà điều kiện logic bảo đảm pattern đã khớp. Bài viết tập trung vào cú pháp ổn định của Java 21, với các ví dụ dùng `instanceof`, biểu thức boolean, nested record patterns và `switch`.

## 1. Biến được khai báo trong record pattern

Giả sử có record:

```java
record Point(int x, int y) {
}
```

Có thể kiểm tra một đối tượng và lấy hai component bằng record pattern:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println("x = " + x);
    System.out.println("y = " + y);
}
```

Trong `Point(int x, int y)`:

- `Point` là kiểu record cần khớp.
- `x` là pattern variable nhận giá trị component thứ nhất.
- `y` là pattern variable nhận giá trị component thứ hai.
- Thứ tự component trong pattern phải tương ứng với thứ tự khai báo trong header của record.

Tên biến trong pattern do người viết chọn; không bắt buộc trùng với tên component. Ví dụ `Point(int horizontal, int vertical)` vẫn lấy lần lượt component thứ nhất và thứ hai. Việc đổi tên biến không thay đổi thứ tự hoặc ý nghĩa dữ liệu được deconstruct.

Pattern chỉ khớp khi đối tượng có kiểu phù hợp với `Point` và các component pattern bên trong cũng khớp. Khi matching thành công, các biến `x` và `y` được khởi tạo từ các component tương ứng. Nếu matching thất bại, không có đường thực thi nào được phép sử dụng những biến đó như thể chúng đã được khởi tạo.

## 2. Phạm vi trong nhánh `if` thành công

Với `instanceof`, pattern variable có thể được sử dụng trong nhánh `if` khi điều kiện đúng:

```java
record Point(int x, int y) {
}

public class BasicPatternScope {
    static void printPoint(Object value) {
        if (value instanceof Point(int x, int y)) {
            System.out.println(x + ", " + y);
            int sum = x + y;
            System.out.println("sum = " + sum);
        }

        // x và y không thuộc phạm vi ở đây.
    }
}
```

Trình biên dịch bảo đảm thân `if` chỉ được thực thi khi `value` khớp với record pattern. Vì vậy, `x` và `y` chắc chắn đã được gán trong thân khối.

Sau khi kết thúc khối `if`, pattern variable không còn trong phạm vi. Đoạn mã sau không hợp lệ:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x);
}

System.out.println(y); // lỗi: y không nằm trong phạm vi
```

Không nên xem pattern variable như biến được khai báo ở đầu method. Phạm vi của nó gắn với điều kiện matching và luồng điều khiển dẫn đến vị trí sử dụng.

## 3. Sử dụng biến trong biểu thức `&&`

Với toán tử AND có đoản mạch (`&&`), toán hạng bên phải chỉ được đánh giá khi toán hạng bên trái là `true`. Do đó, nếu pattern nằm ở bên trái và khớp thành công, các biến của pattern có thể được sử dụng trong phần bên phải:

```java
record Point(int x, int y) {
}

class PointChecks {
    static boolean isInFirstQuadrant(Object value) {
        return value instanceof Point(int x, int y)
                && x > 0
                && y > 0;
    }
}
```

Luồng thực thi bảo đảm rằng `x` và `y` chỉ được tham chiếu khi vế `instanceof` đã trả về `true`. Các biến này cũng có thể được sử dụng trong thân `if`:

```java
class DiagonalPointCheck {
    static void printIfDiagonal(Object value) {
        if (value instanceof Point(int x, int y) && x == y) {
            System.out.println("Point nằm trên đường y = x");
            System.out.println("tọa độ = " + x);
        }
    }
}
```

Nếu vế `instanceof` trả về `false`, Java bỏ qua các vế sau của `&&`, vì thế không có tình huống nào đọc `x` hoặc `y` khi chúng chưa được tạo.

## 4. Sử dụng biến sau điều kiện phủ định và thoát sớm

Một mẫu thường gặp là phủ định điều kiện rồi thoát khỏi method hoặc khối hiện tại khi matching thất bại:

```java
record Point(int x, int y) {
}

class PointDistance {
    static int manhattanDistanceFromOrigin(Object value) {
        if (!(value instanceof Point(int x, int y))) {
            return -1;
        }

        // Đến đây, điều kiện phủ định là false.
        // Điều đó có nghĩa record pattern đã khớp.
        return Math.abs(x) + Math.abs(y);
    }
}
```

Sau câu lệnh `if`, luồng thực thi chỉ có thể tiếp tục nếu điều kiện `!(...)` là `false`. Vì vậy, biểu thức `value instanceof Point(int x, int y)` chắc chắn là `true`, và `x`, `y` nằm trong phạm vi sử dụng sau câu lệnh đó.

Kỹ thuật này thường được gọi là *guard clause* hoặc kiểm tra điều kiện rồi thoát sớm. Nó giúp phần xử lý chính không phải lồng thêm một khối `if` và vẫn giữ được tính an toàn kiểu do trình biên dịch kiểm tra.

Một cách viết tương đương là đặt phần xử lý trong nhánh `else`:

```java
class PointElseDemo {
    static void printCoordinates(Object value) {
        if (!(value instanceof Point(int x, int y))) {
            System.out.println("Không phải Point phù hợp");
        } else {
            System.out.println("Tổng tọa độ: " + (x + y));
        }
    }
}
```

Nhánh `else` chỉ được thực thi khi biểu thức phủ định là `false`, tức pattern đã khớp. Biến `x` và `y` được sử dụng an toàn trong nhánh đó.

## 5. Vì sao không thể dùng biến tùy ý với toán tử `||`?

Toán tử OR có đoản mạch (`||`) chỉ đánh giá vế phải khi vế trái là `false`. Trong ví dụ dưới đây, vế trái chính là biểu thức matching; nếu nó trả về `false`, pattern không khớp và các biến trong pattern chưa được khởi tạo. Vì vậy, không thể tham chiếu các biến ấy ở vế phải:

```java
// Không hợp lệ:
if (value instanceof Point(int x, int y) || x > 0) {
    System.out.println("...");
}
```

Khi vế trái là `false`, Java phải đánh giá `x > 0`, nhưng lúc này `x` chưa có giá trị từ một lần matching thành công. Trình biên dịch từ chối mã này.

Nếu mục tiêu là kiểm tra record rồi tiếp tục kiểm tra component, hãy dùng `&&`:

```java
if (value instanceof Point(int x, int y) && x > 0) {
    System.out.println("x là số dương: " + x);
}
```

Quy tắc không phải là cấm `||` trong mọi biểu thức có pattern. Điều cần bảo đảm là tại từng vị trí sử dụng, mọi đường đi đến vị trí đó đều đã matching thành công. Nếu cấu trúc điều kiện không bảo đảm điều này, pattern variable sẽ không nằm trong phạm vi hợp lệ.

Ví dụ, có thể dùng `||` nếu vế trái được phủ định. Vế phải chỉ chạy khi biểu thức phủ định là `false`, tức record pattern ban đầu đã khớp:

```java
class NegatedPatternOrCheck {
    static boolean isNotPointOrOnXAxis(Object value) {
        return !(value instanceof Point(int x, int y)) || y == 0;
    }
}
```

Nếu `value` không phải `Point`, vế trái là `true` và vế phải được bỏ qua. Nếu vế phải được đánh giá, điều đó chứng minh pattern đã khớp, nên `y` có giá trị hợp lệ để sử dụng. Ví dụ này cho thấy cần xét ý nghĩa luồng điều khiển của cả biểu thức, thay vì chỉ ghi nhớ rằng `||` luôn không dùng được với pattern variable.

## 6. Phạm vi của biến trong nested record patterns

Record pattern có thể lồng nhau để deconstruct các record component nhiều cấp. Ví dụ:

```java
record Point(int x, int y) {
}

record Rectangle(Point topLeft, Point bottomRight) {
}
```

Có thể lấy trực tiếp tọa độ của hai điểm trong một pattern:

```java
class RectangleBounds {
    static void printBounds(Object value) {
        if (value instanceof Rectangle(
                Point(int leftX, int topY),
                Point(int rightX, int bottomY))) {

            int width = rightX - leftX;
            int height = bottomY - topY;
            System.out.println("width = " + width);
            System.out.println("height = " + height);
        }
    }
}
```

Các biến `leftX`, `topY`, `rightX` và `bottomY` được khai báo bởi các pattern ở cấp component lồng nhau. Tất cả đều có thể được sử dụng trong thân `if` vì toàn bộ pattern chỉ khớp khi:

1. `value` khớp với `Rectangle`.
2. Component `topLeft` khớp với record pattern `Point(int leftX, int topY)`.
3. Component `bottomRight` khớp với record pattern `Point(int rightX, int bottomY)`.

Nếu một component không khớp, toàn bộ record pattern thất bại và thân `if` không chạy. Ví dụ, nếu `topLeft` là `null`, nested pattern yêu cầu một `Point` sẽ không khớp. Vì vậy, mã trong thân `if` không phải xử lý trường hợp các biến tọa độ chỉ được khởi tạo một phần.

Tên biến nên mô tả vai trò của dữ liệu. Với pattern lồng nhiều cấp, các tên như `leftX`, `topY`, `rightX`, `bottomY` thường dễ đọc hơn việc đặt tên chung chung `x1`, `y1`, `x2`, `y2` khi nghiệp vụ có ý nghĩa hình học rõ ràng.

## 7. Phạm vi trong `switch` và guard `when`

Record pattern có thể được dùng trong nhãn `case` của switch. Pattern variable nằm trong phạm vi của guard `when` và phần thân của switch rule tương ứng:

```java
record Point(int x, int y) {
}

class PointSwitchExpression {
    static String describe(Object value) {
        return switch (value) {
            case Point(int diagonalX, int diagonalY)
                    when diagonalX == diagonalY -> "Point trên đường y = x";
            case Point(int x, int y) -> "Point(" + x + ", " + y + ")";
            case null -> "null";
            default -> "Giá trị khác";
        };
    }
}
```

Trong nhãn `case` đầu tiên, `diagonalX` và `diagonalY` đã được matching trước khi guard được đánh giá. Do đó guard có thể dùng chúng để kiểm tra điều kiện bổ sung. Nếu pattern khớp nhưng guard trả về `false`, switch tiếp tục xét các nhãn `case` tiếp theo theo quy tắc của switch.

Ở mỗi switch rule, các pattern variable được sử dụng trong biểu thức sau `->` hoặc trong toàn bộ block sau `->`:

```java
record Point(int x, int y) {
}

class PointSwitchStatement {
    static void printDescription(Object value) {
        switch (value) {
            case Point(int x, int y) -> {
                int sum = x + y;
                System.out.println("Tổng tọa độ: " + sum);
            }
            case null -> System.out.println("Không có giá trị");
            default -> System.out.println("Không phải Point");
        }
    }
}
```

`x` và `y` chỉ thuộc rule có pattern `Point(int x, int y)`. Chúng không thể được tham chiếu trong `case null`, `default` hoặc sau switch. Với switch trên reference type, nếu muốn xử lý giá trị `null` một cách tường minh thì dùng nhãn `case null`; nhãn `default` không thay thế cho nhãn này.

## 8. Đặt tên và tránh xung đột biến

Pattern variable là biến cục bộ được khai báo trong pattern. Hãy chọn tên theo vai trò của component và bảo đảm tên không xung đột với biến hoặc tham số khác trong phạm vi chồng lấn.

Ví dụ dễ đọc:

```java
record User(String username, int age) {
}

class UserChecks {
    static void printAdult(Object value) {
        if (value instanceof User(String username, int age)
                && age >= 18) {
            System.out.println(username + " là người trưởng thành");
        }
    }
}
```

Tên `username` và `age` thể hiện ý nghĩa dữ liệu rõ ràng. Nếu component trong record có tên khác, pattern variable vẫn có thể dùng tên riêng miễn là kiểu và vị trí component tương ứng.

Không khai báo lại cùng tên biến trong một phạm vi đang chồng lấn. Ví dụ, nếu method đã có tham số tên `x`, không nên đặt component pattern cũng là `x` trong phạm vi mà quy tắc khai báo biến của Java không cho phép trùng tên. Hãy chọn tên mô tả rõ nghĩa hơn, chẳng hạn `pointX`, `pointY`.

Đối với nested pattern, cần phân biệt tên biến với tên component. Trong `Rectangle(Point(int leftX, int topY), Point(int rightX, int bottomY))`, các tên `leftX` và `topY` là tên biến do pattern khai báo; `topLeft` và `bottomRight` là tên component được khai báo trong record `Rectangle`. Vị trí trong pattern, chứ không phải tên biến, xác định component nào được lấy ra.

## 9. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Dùng pattern variable sau khi kết thúc `if` | Biến chỉ nằm trong phạm vi được flow scoping xác định | Chuyển phần xử lý vào nhánh thành công hoặc dùng guard clause để tiếp tục sau khi đã khớp |
| Dùng biến pattern ở vế phải của `||` | Vế phải có thể chạy khi pattern ở vế trái thất bại | Dùng `&&` nếu vế phải phụ thuộc vào dữ liệu được deconstruct |
| Dùng component của nested pattern khi một cấp chưa khớp | Toàn bộ pattern có thể thất bại nếu record hoặc component lồng nhau không phù hợp | Đặt phần xử lý trong nhánh hoặc switch rule mà toàn bộ nested pattern đã khớp |
| Nhầm tên biến với tên component | Tên biến trong pattern do người viết chọn, còn vị trí component theo record header | Kiểm tra thứ tự khai báo component và đặt tên biến theo ý nghĩa dữ liệu |
| Dùng biến của một switch rule ở rule khác | Pattern variable chỉ thuộc phạm vi của rule tương ứng | Đưa xử lý vào đúng rule hoặc truyền giá trị ra qua kết quả/biến riêng có phạm vi phù hợp |
| Giả định `default` xử lý cả `null` trong switch | Với switch trên reference type, `null` cần được xử lý bằng `case null` nếu muốn tránh hành vi ném `NullPointerException` | Bổ sung `case null` khi hợp đồng đầu vào cho phép null |

Khi gặp lỗi biên dịch liên quan đến pattern variable, hãy đọc điều kiện bao quanh vị trí sử dụng. Câu hỏi quan trọng là: mọi đường thực thi có thể đến dòng này đều đã chứng minh pattern khớp hay chưa?

## 10. Ví dụ tổng hợp

Ví dụ sau kết hợp `instanceof`, nested record pattern, toán tử `&&`, guard clause và switch pattern:

```java
record Point(int x, int y) {
}

record Rectangle(Point topLeft, Point bottomRight) {
}

public class RecordPatternFlowDemo {
    static int area(Object value) {
        if (!(value instanceof Rectangle(
                Point(int leftX, int topY),
                Point(int rightX, int bottomY)))) {
            return 0;
        }

        int width = Math.abs(rightX - leftX);
        int height = Math.abs(bottomY - topY);
        return width * height;
    }

    static boolean isOrigin(Object value) {
        return value instanceof Point(int x, int y)
                && x == 0
                && y == 0;
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 -> "origin";
            case Point(int x, int y) -> "point";
            case Rectangle rectangle -> "rectangle";
            case null -> "null";
            default -> "other";
        };
    }
}
```

Trong method `area`, khi chương trình đi qua câu lệnh `if`, nested record pattern chắc chắn đã khớp; vì thế bốn biến tọa độ có thể được sử dụng ở phần tính toán phía sau. Trong `isOrigin`, các biến chỉ được dùng ở các vế phải của `&&`, nơi matching đã thành công. Trong `classify`, biến của mỗi pattern chỉ được dùng trong guard hoặc rule tương ứng.

## Kết luận

Trong Java 21, phạm vi của pattern variable được xác định theo luồng điều khiển: biến chỉ được sử dụng tại vị trí mà trình biên dịch chứng minh pattern đã khớp. Hãy tận dụng nhánh thành công của `if`, toán tử `&&`, guard clause và switch rule để sử dụng dữ liệu đã deconstruct an toàn. Với nested record patterns, toàn bộ pattern phải khớp trước khi các component variable có thể được sử dụng. Đặt tên biến theo vai trò dữ liệu và luôn nhớ rằng thứ tự component trong pattern phải khớp với thứ tự khai báo trong record.
