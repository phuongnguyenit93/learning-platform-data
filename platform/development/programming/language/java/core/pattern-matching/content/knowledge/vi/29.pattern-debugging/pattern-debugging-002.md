# Đặt breakpoint trong guarded case của switch (Java 21+)

## 1. Mục tiêu: tìm đúng vị trí điều kiện bị loại

Từ Java 21, `switch` hỗ trợ **pattern matching** và **guard `when`**. Một nhánh guarded case gồm hai bước quyết định:

1. **Pattern có khớp selector không?** Ví dụ `Login(User(var name, var active), var failedAttempts)` có nhận đúng cấu trúc đối tượng không?
2. **Guard có trả `true` không?** Ví dụ `when canEnter(name, active, failedAttempts)` có chấp nhận các giá trị vừa phân rã không?

Chỉ khi **cả hai** đều thỏa, Java mới chọn nhánh và chạy phần thân bên phải dấu `->`. Nếu pattern không khớp, guard **không được đánh giá**; nếu pattern khớp nhưng guard sai, Java tiếp tục xét các nhánh `case` phù hợp phía sau.

Khi debug, điều này dẫn đến một nhầm lẫn phổ biến: **đặt breakpoint chỉ trong thân guarded case rồi kết luận mã không chạy**. Breakpoint ở thân có thể không được chạm vì pattern sai **hoặc** guard trả false. Nó không giúp phân biệt hai nguyên nhân đó.

Bài này hướng dẫn đặt breakpoint tại đúng các điểm quan sát để trả lời:

- Selector thực tế có kiểu và giá trị gì?
- Các record pattern lồng nhau đã khớp chưa?
- Biến pattern nào có thể quan sát được và ở phạm vi nào?
- Guard được gọi hay bị bỏ qua? Giá trị nào làm guard sai?
- Khi guarded case không được chọn, mã rơi vào nhánh dự phòng nào?
- Làm sao tạo điểm dừng ổn định khi IDE/JVM không cho đặt breakpoint trực tiếp trên từng đoạn của `when`?

Ví dụ dùng **JDK 21+**, không cần bật preview. Các thao tác IDE được mô tả theo nguyên tắc chung của trình gỡ lỗi Java; tên nút hoặc khả năng đặt breakpoint trực tiếp trên biểu thức `when` có thể khác nhau giữa IDE và bản biên dịch.

## 2. Hiểu thứ tự đánh giá trước khi đặt breakpoint

Xét một mẫu nhỏ:

~~~java
case Login(User(var name, var active), var failedAttempts)
        when canEnter(name, active, failedAttempts) -> {
    String result = "ALLOW:" + name;
    yield result;
}
~~~

Đây là **một nhánh nằm trong switch expression**, chưa phải chương trình độc lập. Nó hoạt động theo luồng sau:

~~~text
Có selector đầu vào
        |
        v
Khớp Login(...) ?
   | không   | có
   v         v
Nhánh khác   Khớp component User(...) ?
             | không    | có
             v          v
             Nhánh khác Gắn name, active, failedAttempts
                        |
                        v
                 Gọi canEnter(...)
                    | false    | true
                    v          v
                 Nhánh khác   Chạy thân -> và yield
~~~

Ba vị trí quan sát khác nhau có giá trị khác nhau:

| Vị trí breakpoint | Khi nào dừng? | Điều có thể suy ra |
| --- | --- | --- |
| Trước `switch` | Mỗi lần đi qua phương thức | Có thể xem selector gốc; chưa biết pattern nào khớp |
| Trong hàm `canEnter` được gọi từ `when` | Khi pattern đã khớp và guard được đánh giá | Biết rõ guard đã chạy; kiểm tra đầu vào và điều kiện con |
| Tại lệnh thực thi trong thân guarded case | Chỉ khi pattern khớp **và** guard đúng | Nhánh đã được chọn; biến pattern có phạm vi hợp lệ |
| Trong thân nhánh dự phòng cùng loại `Login` | Khi các nhánh `Login` cụ thể trước đó không được chọn | Xác định đường đi thất bại; cần xem thêm nhánh nào bị loại |
| Trong `case null` hoặc `default` nếu có thân thực thi | Khi đi vào nhánh tương ứng | Phân biệt selector null với kiểu không hỗ trợ |

**Kết luận:** đặt breakpoint ở phần thân nhánh được chọn không thể cho biết **vì sao** nhánh không được chọn. Muốn kiểm tra guard false, đặt breakpoint **trong hàm guard** hoặc tại nhánh dự phòng tương ứng.

## 3. Chọn bài toán có guard dễ kiểm thử

Giả sử ứng dụng định tuyến lệnh đăng nhập:

~~~java
record User(String name, boolean active) {}
record Login(User user, int failedAttempts) {}
record Logout(String userId) {}
~~~

Một `Login` được cho phép khi:

1. Record `User` tồn tại, không phải null.
2. `name` không null và không toàn khoảng trắng.
3. `active == true`.
4. Số lần đăng nhập thất bại thuộc khoảng `0 <= failedAttempts < 3`.

Nếu `Login` chứa một `User` nhưng vi phạm một quy tắc, trả về `"DENY:policy"`. Nếu `Login.user == null`, trả về `"DENY:no-user"`. Với `Logout`, yêu cầu `userId` không null và không trắng.

Ở đây record đầu vào **cố ý không có constructor validation**. Mục tiêu là mô phỏng dữ liệu chưa kiểm tra để quan sát cách pattern và guard hoạt động. Trong ứng dụng thật, những invariant bắt buộc có thể được bảo vệ sớm hơn ở constructor hoặc boundary.

Ta tách guard thành một hàm có tên dễ hiểu:

~~~java
static boolean canEnter(String name, boolean active, int failedAttempts) {
    boolean validName = name != null && !name.isBlank();
    boolean validAttempts = failedAttempts >= 0 && failedAttempts < 3;
    boolean result = validName && active && validAttempts;
    return result;
}
~~~

**Vì sao tách hàm?** Vì đây là nơi đáng đặt breakpoint nhất. IDE thường tạo vị trí dừng ổn định ở các câu lệnh `boolean validName = ...` hoặc `boolean result = ...`, giúp xem từng điều kiện thay vì cố đặt breakpoint vào một biểu thức `when` dài mà thông tin dòng lệnh có thể không chi tiết.

Lưu ý: hàm `canEnter` phải **không làm thay đổi trạng thái**. Guard được dùng để quyết định chọn nhánh, nên tránh I/O, tăng bộ đếm, ghi database hoặc thay đổi đối tượng bên trong guard. Khi debug, việc Evaluate Expression hoặc logpoint đánh giá lại biểu thức có side effect cũng có thể làm sai đường đi thực tế.

## 4. Dùng breakpoint trước selector và trong guard

Phương thức định tuyến:

~~~java
static String route(Object input) {
    return switch (input) {
        case null -> "IGNORED:null";

        case Login(User(var name, var active), var failedAttempts)
                when canEnter(name, active, failedAttempts) -> {
            String result = "ALLOW:" + name;
            yield result;
        }

        case Login(User(var name, var active), var failedAttempts) -> {
            String result = "DENY:policy";
            yield result;
        }

        case Login(var user, var failedAttempts) -> {
            String result = "DENY:no-user";
            yield result;
        }

        case Logout(var id) when id != null && !id.isBlank() ->
                "LOGOUT:" + id;

        case Logout(var id) -> "DENY:logout-id";
        default -> "IGNORED:type";
    };
}
~~~

Đây là phương thức của lớp có ba record `User`, `Login` và `Logout`. Mục 9 cung cấp cả lớp và hàm `main`.

### Bước 1 — dừng trước `switch`

Đặt breakpoint tại dòng `return switch (input) {` hoặc một dòng thực thi ổn định ngay trước đó (có thể thêm biến cục bộ tạm khi đang debug).

Xem:

- `input == null` hay không?
- Runtime type của `input` là `Login`, `Logout` hay kiểu khác?
- Nếu `input` là `Login`, giá trị `user` và `failedAttempts` là gì?
- Nếu `user == null`, mẫu lồng `User(...)` **không khớp**, nên guard `canEnter` không được gọi cho nhánh này.

Ở vị trí trước `switch`, các biến pattern `name` và `active` **chưa được khai báo trong phạm vi hiện tại**; chỉ nên xem selector và những field/accessor của nó một cách an toàn. Đừng cố Evaluate Expression với `name` trước khi pattern đã khớp.

### Bước 2 — dừng ở `canEnter`

Đặt breakpoint tại:

~~~java
boolean validName = name != null && !name.isBlank(); // BP-GUARD-NAME
~~~

Khi dừng ở đây, trình gỡ lỗi có thể hiển thị các tham số `name`, `active` và `failedAttempts`. Tiếp tục **Step Over** tới dòng:

~~~java
boolean result = validName && active && validAttempts; // BP-GUARD-RESULT
~~~

Lúc này có thể xem `validName` và `validAttempts` đã được tính, rồi bước tiếp để xem `result`. Nếu giá trị null, `name != null` sẽ chặn `name.isBlank()` nhờ đánh giá ngắn mạch.

**Điểm rất quan trọng:** nếu `input` là `Login(null, 0)`, breakpoint trong `canEnter` **không dừng** từ lần gọi này, bởi `User(...)` trong mẫu lồng không khớp. Nếu `input` là `Login(new User(null, true), 0)` thì `User` tồn tại, mẫu `var name` nhận null; `canEnter` **vẫn được gọi** và `validName` sẽ là false.

### Bước 3 — dừng trong thân guarded case

Đặt breakpoint ở lệnh thực thi:

~~~java
String result = "ALLOW:" + name; // BP-ALLOW
~~~

Nếu breakpoint dừng tại đây, chắc chắn **mẫu và guard của nhánh đó đã thành công**, nên có thể xem `name`, `active` và `failedAttempts` trong phạm vi của nhánh. Thân `switch expression` dùng `yield result;` để trả kết quả; `yield` khác với `return` của phương thức bao ngoài.

Nếu breakpoint **không** dừng, cần kiểm tra `canEnter` đã được gọi chưa và nhánh dự phòng nào nhận selector. Không nên kết luận ngay rằng Java “bỏ qua case”.

## 5. Đặt breakpoint ở các nhánh dự phòng để tìm đường rơi

Trong ví dụ có hai nhánh dự phòng quan trọng:

~~~java
case Login(User(var name, var active), var failedAttempts) -> {
    String result = "DENY:policy";  // BP-DENY-POLICY
    yield result;
}

case Login(var user, var failedAttempts) -> {
    String result = "DENY:no-user"; // BP-DENY-USER
    yield result;
}
~~~

Nhánh `DENY:policy` có cùng **record pattern lồng** như nhánh được phép nhưng **không có guard**. Nếu guard của nhánh trước trả false, nhánh này có thể nhận giá trị. Ví dụ:

- `User("Lan", false)`: pattern khớp; `canEnter` chạy và trả false vì `active == false`.
- `User("Lan", true)` với `failedAttempts == 3`: guard trả false vì đạt ngưỡng.
- `User(null, true)`: mẫu `User(var name, ...)` khớp, nhưng guard trả false vì tên null.

Nhánh `DENY:no-user` chứa `Login(var user, var failedAttempts)`, không đòi `user` phải là record `User` khác null. Một `Login(null, 0)` có thể rơi vào đây vì hai nhánh chứa `User(...)` không khớp ở tầng record lồng.

**Cảnh báo quan trọng về `var`:** mẫu component `var user` có thể nhận null. `var` là suy luận kiểu chứ không phải validation. Việc một mẫu rộng hơn khớp không có nghĩa dữ liệu đã hợp lệ theo domain.

Đặt cả ba breakpoint `BP-GUARD-NAME`, `BP-DENY-POLICY` và `BP-DENY-USER` giúp tạo bảng quan sát:

| Input | Guard có được gọi? | Nhánh kết thúc | Kết quả |
| --- | --- | --- | --- |
| `Login(User("Lan", true), 2)` | Có, trả true | `BP-ALLOW` | `ALLOW:Lan` |
| `Login(User("Lan", true), 3)` | Có, trả false | `BP-DENY-POLICY` | `DENY:policy` |
| `Login(User(null, true), 1)` | Có, trả false | `BP-DENY-POLICY` | `DENY:policy` |
| `Login(null, 0)` | Không | `BP-DENY-USER` | `DENY:no-user` |
| `Logout("A1")` | Không, vì nhánh `Login` không khớp | Nhánh `Logout` | `LOGOUT:A1` |
| `null` | Không | `case null` | `IGNORED:null` |

Như vậy, **breakpoint ở nơi guard đánh giá** và **breakpoint ở nơi chương trình rơi xuống** bổ sung cho nhau, thay vì cố gắng tìm mọi nguyên nhân bằng một breakpoint trên mũi tên `->`.

## 6. Vì sao breakpoint trực tiếp trên `when` đôi khi khó dùng?

Đoạn:

~~~java
case Login(User(var name, var active), var failedAttempts)
        when name != null && !name.isBlank()
                && active && failedAttempts < 3 -> {
    // ...
}
~~~

là cú pháp hợp lệ về cấu trúc khi nằm trong một `switch` thích hợp; tuy nhiên ví dụ còn thiếu quy tắc `failedAttempts >= 0` nên **không hoàn toàn tương đương** với hàm `canEnter` phía trên. Đây là đoạn minh họa, không phải mã thay thế trong tệp chính.

Về việc gỡ lỗi:

- IDE có thể cho phép breakpoint tại một số vị trí trên dòng `case` hoặc `when`, nhưng độ chính xác phụ thuộc **debug information**, cách compiler ánh xạ biểu thức ra bytecode và debugger.
- Một breakpoint đặt trên dòng `when` có thể được IDE **dịch tới một vị trí thực thi khác**; không nên coi mọi điều kiện con trong `&&` đều có một line breakpoint riêng.
- **Step Into** khi đang ở dòng gọi guard có thể vào `canEnter`. Khi cần quan sát cả guard true lẫn false, cách ổn định là đặt breakpoint trực tiếp trong hàm.
- Nếu guard chỉ là biểu thức dài không gọi hàm, có thể tạm thời **Extract Method** thành một hàm thuần với tên nói lên nghiệp vụ, hoặc đặt một breakpoint ở nhánh dự phòng để đối chiếu.
- Nếu compiler hoặc IDE không dừng nơi dự kiến, đừng thay đổi logic nghiệp vụ bừa bãi chỉ để ép breakpoint. Hãy xem **dòng executable**, điểm break được IDE xác nhận, thông tin debug và stack frame hiện tại.

Khi debug tình huống phức tạp, một hàm `canEnter` nhỏ còn giúp viết unit test trực tiếp cho các điều kiện, thay vì chỉ dựa vào việc tạm dừng chương trình trong IDE.

## 7. Conditional breakpoint, logpoint và Evaluate Expression

Sau khi biết đúng điểm dừng, có thể giảm nhiễu bằng các kỹ thuật sau.

### Conditional breakpoint

Nếu chỉ muốn dừng khi số lượt thất bại đạt ngưỡng, đặt breakpoint trong `canEnter` với điều kiện ví dụ:

~~~java
failedAttempts == 3
~~~

Biểu thức điều kiện của breakpoint được đánh giá trong **ngữ cảnh đang dừng**. Nếu breakpoint nằm trong `canEnter`, `failedAttempts` là tham số của hàm; nếu nằm trước `switch`, biến pattern chưa chắc có phạm vi nên cần đánh giá dựa trên `input`.

Khi filter theo tên:

~~~java
name == null
~~~

hãy bảo đảm breakpoint nằm trong hàm có tham số `name` hoặc trong nhánh nơi biến mẫu có phạm vi. Một biểu thức như `name.equals("Lan")` **không an toàn** nếu `name` có thể null; chọn `"Lan".equals(name)` hoặc điều kiện null an toàn.

### Logpoint (breakpoint ghi log)

Nếu IDE hỗ trợ logpoint, có thể ghi các giá trị `name`, `active`, `failedAttempts` khi vào guard mà không tạm dừng mọi lượt. Cần tránh đưa thông tin cá nhân, credential hoặc mã bảo mật vào log của môi trường thật.

Logpoint nên có biểu thức đơn giản, không có side effect. Nó không thay thế việc kiểm tra nguyên nhân logic: một logpoint trong thân `BP-ALLOW` chỉ xuất hiện khi guard đã đúng; muốn biết guard false phải ghi ở `canEnter` hoặc nhánh dự phòng.

### Evaluate Expression và Watches

Khi dừng tại `BP-GUARD-RESULT`, có thể kiểm tra:

~~~java
validName
active
validAttempts
validName && active && validAttempts
~~~

Các dòng trên là **biểu thức để nhập riêng trong cửa sổ Evaluate Expression/Watches**, không phải mã Java hoàn chỉnh. Không cần sửa code để in tất cả giá trị.

Hạn chế đánh giá các getter/hàm có side effect trong Watches hoặc biểu thức điều kiện: một debugger có thể đánh giá lại chúng nhiều lần. Hàm guard nên thuần để quan sát không làm đổi kết quả.

### Exception breakpoint

Nếu chương trình ném `NullPointerException` hoặc một exception bất ngờ, **exception breakpoint** có thể giúp tìm vị trí phát sinh. Nhưng exception breakpoint **không cho biết mọi lần guard false**, vì guard false là luồng điều khiển bình thường, không phải exception.

## 8. Quy trình debug có hệ thống cho một guarded case

Một quy trình thực tế có thể áp dụng trong IntelliJ IDEA, Eclipse hoặc VS Code với Java debugger phù hợp:

1. **Biên dịch có thông tin debug.** Dùng `javac -g --release 21 ...`; cờ `-g` yêu cầu tạo thông tin debug, bao gồm thông tin biến cục bộ.
2. **Chọn ca tái hiện tối thiểu.** Thay vì chạy toàn bộ hệ thống, xác định một input mà guarded case không được chọn như mong đợi.
3. **Dừng trước `switch`.** Xem kiểu runtime và giá trị selector; kiểm tra record lồng có thể null không.
4. **Đặt breakpoint trong hàm guard.** Xác nhận guard có thực sự được gọi. Nếu không, xem xét pattern hoặc một case trước đã xử lý input.
5. **Step Over từng điều kiện.** Tìm biến boolean nào chuyển false; chú ý thứ tự ngắn mạch của `&&` và khả năng null.
6. **Đặt breakpoint trong thân nhánh được chọn và nhánh dự phòng.** Xác định code chạy ở đâu sau khi guard true/false.
7. **Xem phạm vi biến mẫu.** Biến `name`, `active`, `failedAttempts` có phạm vi sau khi pattern khớp, không có sẵn ở mọi nhánh hoặc trước `switch`.
8. **Kiểm tra thứ tự case.** Case tổng quát đứng trước có thể làm case cụ thể bị dominated hoặc thay đổi đường chọn nhánh; `case null` cần xử lý selector null nếu API cho phép.
9. **Rút gọn nguyên nhân thành test.** Khi hiểu vấn đề, viết assertion cho ca đó để tránh lỗi tái diễn.
10. **Dọn breakpoint và instrumentation tạm.** Không để lại log chứa dữ liệu nhạy cảm hoặc thay đổi logic chỉ phục vụ debug.

**Lưu ý về bước qua chương trình:** `Step Over` thực thi câu lệnh hiện tại mà không đi vào lời gọi phương thức; `Step Into` có thể đi vào `canEnter`; `Resume` tiếp tục tới breakpoint tiếp theo. Khi nhiều lời gọi được thực hiện liên tiếp, debugger có thể dừng nhiều lần ở cùng một breakpoint; đọc **call stack** và giá trị đầu vào để phân biệt từng lượt.

## 9. Chương trình Java 21 hoàn chỉnh, có vị trí breakpoint rõ ràng

Lưu thành **`GuardedCaseBreakpointsDemo.java`**. Các comment `BP-*` là vị trí gợi ý đặt breakpoint trên **dòng có mã thực thi**.

~~~java
public class GuardedCaseBreakpointsDemo {
    record User(String name, boolean active) {}
    record Login(User user, int failedAttempts) {}
    record Logout(String userId) {}

    private static int passed = 0;

    static boolean canEnter(String name, boolean active, int failedAttempts) {
        boolean validName = name != null && !name.isBlank(); // BP-GUARD-NAME
        boolean validAttempts = failedAttempts >= 0 && failedAttempts < 3;
        boolean result = validName && active && validAttempts; // BP-GUARD-RESULT
        return result;
    }

    static String route(Object input) {
        return switch (input) {
            case null -> "IGNORED:null";

            case Login(User(var name, var active), var failedAttempts)
                    when canEnter(name, active, failedAttempts) -> {
                String result = "ALLOW:" + name; // BP-ALLOW
                yield result;
            }

            case Login(User(var name, var active), var failedAttempts) -> {
                String result = "DENY:policy"; // BP-DENY-POLICY
                yield result;
            }

            case Login(var user, var failedAttempts) -> {
                String result = "DENY:no-user"; // BP-DENY-USER
                yield result;
            }

            case Logout(var id) when id != null && !id.isBlank() ->
                    "LOGOUT:" + id;

            case Logout(var id) -> "DENY:logout-id";
            default -> "IGNORED:type";
        };
    }

    static void check(String label, Object input, String expected) {
        String actual = route(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("accepted",
                new Login(new User("Lan", true), 2), "ALLOW:Lan");
        check("accepted-zero",
                new Login(new User("Lan", true), 0), "ALLOW:Lan");
        check("at-limit",
                new Login(new User("Lan", true), 3), "DENY:policy");
        check("inactive",
                new Login(new User("Lan", false), 1), "DENY:policy");
        check("blank-name",
                new Login(new User("  ", true), 1), "DENY:policy");
        check("null-name",
                new Login(new User(null, true), 1), "DENY:policy");
        check("negative-count",
                new Login(new User("Lan", true), -1), "DENY:policy");
        check("missing-user", new Login(null, 0), "DENY:no-user");
        check("logout-ok", new Logout("A1"), "LOGOUT:A1");
        check("logout-blank", new Logout(" "), "DENY:logout-id");
        check("logout-null", new Logout(null), "DENY:logout-id");
        check("null-selector", null, "IGNORED:null");
        check("other-type", 42, "IGNORED:type");

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac -g --release 21 GuardedCaseBreakpointsDemo.java
java GuardedCaseBreakpointsDemo
~~~

Cờ `-g` thuận tiện cho debugger, còn `--release 21` yêu cầu biên dịch theo API và ngôn ngữ Java 21. Khi chạy phiên bản build bằng công cụ khác (Maven, Gradle, IDE), bảo đảm cấu hình source/release và thông tin debug tương ứng.

**Output chính xác:**

~~~text
PASS accepted -> ALLOW:Lan
PASS accepted-zero -> ALLOW:Lan
PASS at-limit -> DENY:policy
PASS inactive -> DENY:policy
PASS blank-name -> DENY:policy
PASS null-name -> DENY:policy
PASS negative-count -> DENY:policy
PASS missing-user -> DENY:no-user
PASS logout-ok -> LOGOUT:A1
PASS logout-blank -> DENY:logout-id
PASS logout-null -> DENY:logout-id
PASS null-selector -> IGNORED:null
PASS other-type -> IGNORED:type
ALL PASSED: 13
~~~

### Ba thí nghiệm breakpoint nên thực hiện

**Thí nghiệm A — guard đúng:** đặt breakpoint ở `BP-GUARD-NAME` và `BP-ALLOW`, chạy ca `accepted`. Debugger đi vào `canEnter`, cho thấy `validName == true` và `validAttempts == true`; sau đó chương trình chọn nhánh `ALLOW`.

**Thí nghiệm B — guard sai:** đặt breakpoint ở `BP-GUARD-RESULT` và `BP-DENY-POLICY`, chạy ca `at-limit`. `failedAttempts == 3` làm `validAttempts == false`; nhánh `ALLOW` không chạy, sau đó `DENY:policy` được chọn.

**Thí nghiệm C — pattern không khớp:** đặt breakpoint ở `BP-GUARD-NAME` và `BP-DENY-USER`, chạy ca `missing-user`. `Login` khớp ở ngoài, nhưng `User(...)` không khớp khi `user == null`. Vì vậy hàm `canEnter` không được gọi, nhánh `DENY:no-user` tiếp nhận dữ liệu.

Ở cả ba thí nghiệm, dùng **Resume** để đi tới breakpoint tiếp theo; nếu chạy tất cả 13 ca liên tiếp, breakpoint trong `canEnter` sẽ được chạm nhiều lần. Để quan sát riêng một tình huống, có thể tạm tạo một phương thức gọi `route` với một input hoặc dùng conditional breakpoint thay vì lẫn nhiều lượt chạy.

### Vì sao các assertion có giá trị?

Phương thức `check` không chỉ in kết quả. Nó so sánh kết quả `route(input)` với chuỗi kỳ vọng và ném `AssertionError` nếu khác. Vì vậy `ALL PASSED: 13` chỉ xuất hiện khi toàn bộ ca đều đúng. Những ca null, tên trắng và số lần thất bại âm giúp quan sát những đường đi mà kiểm thử happy path thường bỏ sót.

## 10. Lỗi debugging dễ gặp

**Lỗi 1 — chỉ đặt breakpoint trong thân guarded case.** Không dừng không cho biết pattern sai hay guard false. Hãy thêm breakpoint trong hàm guard và nhánh dự phòng.

**Lỗi 2 — chờ guard chạy dù nested record không khớp.** Với `Login(null, 0)`, mẫu `User(...)` thất bại trước khi gọi `canEnter`. Cần xem selector ở trước `switch` hoặc dừng ở nhánh `Login(var user, ...)` rộng hơn.

**Lỗi 3 — hiểu nhầm `var` bảo đảm khác null.** `var name` và `var user` có thể nhận null từ record component; phải kiểm tra theo hợp đồng trước khi gọi phương thức.

**Lỗi 4 — nghĩ có breakpoint trên mỗi vế của `&&`.** JVM/IDE làm việc với bytecode và line number/debug info; một biểu thức ghép dài không nhất thiết có vị trí dừng riêng cho từng toán hạng. Extract Method hoặc tính từng giá trị trung gian nếu cần quan sát.

**Lỗi 5 — đặt breakpoint trong guard có side effect.** Một expression evaluator hoặc logpoint có thể gọi lại phương thức, gây thay đổi trạng thái. Giữ guard và expression trong debugger **thuần**, tránh các lệnh ảnh hưởng dữ liệu.

**Lỗi 6 — dùng `default` để giải thích mọi input.** `case null` là trường hợp riêng; `default` trong pattern switch không tự nhận selector null. Không khớp các subtype khác cũng không có nghĩa guard của một subtype đã được gọi.

**Lỗi 7 — đọc biến pattern ở nơi nó chưa có phạm vi.** `name` chỉ khả dụng trong guard và thân nhánh khi mẫu tương ứng đã khớp; trước `switch` hay tại nhánh khác có thể không thấy biến đó.

**Lỗi 8 — đảo nhánh dự phòng lên trước nhánh guarded.** Một nhánh tổng quát có thể che nhánh cụ thể, khiến compiler báo dominated hoặc thay đổi khả năng chọn nhánh. Giữ guarded case trước fallback của cùng variant.

**Lỗi 9 — xem sự vắng mặt của breakpoint là lỗi compiler.** Có thể input không đi tới nhánh, mã đã được biên dịch khác, class chạy không phải class đang mở hoặc IDE dịch breakpoint đến vị trí khác. Xác nhận call stack, class đang chạy, build và vị trí executable.

**Lỗi 10 — quên biến đường đi debug thành test tự động.** Breakpoint giúp tìm nguyên nhân tại một thời điểm; regression test giữ cho hành vi không bị sai lại khi refactor.

## 11. Checklist khi một guarded case “không chạy”

1. Selector của `switch` thực sự được truyền vào là gì?
2. Case có được đặt **sau** một nhánh bao quát hơn hoặc bị dominated không?
3. Selector có đúng kiểu của pattern ngoài không?
4. Component record lồng có thể bằng null, khiến mẫu con không khớp không?
5. Hàm trong `when` đã được gọi chưa? Nếu không, có phải pattern không khớp?
6. Guard nào false? Điều kiện `name != null`, `active` hay ngưỡng `failedAttempts`?
7. Khi guard false, case dự phòng nào được chọn?
8. Breakpoint đặt trên dòng thực thi thực sự và debug info có sẵn không?
9. Có dùng breakpoint condition/logpoint khiến biểu thức bị đánh giá lại hoặc có side effect không?
10. Đã tạo test xác minh cả nhánh true, false, null và không khớp kiểu chưa?

### Bài tập tự luyện

- Thay ngưỡng `failedAttempts < 3` thành `failedAttempts < 5`. Đặt breakpoint tại `BP-GUARD-RESULT`, kiểm tra input có giá trị 3 rồi cập nhật kỳ vọng `at-limit` cho đúng quy tắc mới.
- Đặt conditional breakpoint `name == null` trong `canEnter`. So sánh hành vi của `null-name` và `missing-user`; giải thích vì sao chỉ một ca có thể chạm breakpoint trong guard.
- Tạm đổi `Login(User(...))` thành `Login(var user, ...)` và viết guard kiểm tra `user != null`. Đặt breakpoint để xem thứ tự kiểm tra thay đổi như thế nào.
- Tạo một `case Login(...)` dự phòng trả về mã lỗi cụ thể cho `failedAttempts < 0`; quan sát thứ tự case và cập nhật test `negative-count`.
- Chuyển kết quả sang một `sealed interface Decision` với hai record `Allowed`, `Denied`. Dùng `switch` exhaustive để in kết quả và đặt breakpoint ở mỗi nhánh.

**Ghi nhớ:** Với guarded case, có **ba câu hỏi khác nhau**: *pattern đã khớp chưa*, *guard đã được gọi và trả gì*, và *case nào thực sự chạy*. Đặt breakpoint trước `switch` để xem selector, trong **hàm guard** để quan sát điều kiện true/false, và trong **thân guarded case cùng nhánh dự phòng** để xác nhận đường điều khiển. Đừng chỉ dựa vào breakpoint ở dấu `->` hoặc nhầm việc guard không chạy với việc guard trả false.