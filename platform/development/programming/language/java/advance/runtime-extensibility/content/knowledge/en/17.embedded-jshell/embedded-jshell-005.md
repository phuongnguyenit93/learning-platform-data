# Quản lý phụ thuộc giữa các đoạn mã, khai báo lại và drop trong JShell nhúng

## 1. Vì sao snippet trong JShell không độc lập?

Khi nhúng JShell vào ứng dụng Java, bạn không chỉ thực thi từng chuỗi mã riêng lẻ. Một phiên \`jdk.jshell.JShell\` lưu trạng thái gồm các **snippet**: khai báo biến, phương thức, kiểu, import và biểu thức/lệnh. Snippet sau có thể dùng tên do snippet trước khai báo; khi một khai báo bị thay thế hoặc bị loại bỏ, các snippet phụ thuộc có thể đổi trạng thái.

Ví dụ trong một phiên JShell:

\`\`\`java
int factor = 2;
int multiply(int x) { return x * factor; }
multiply(3);
\`\`\`

Phương thức \`multiply\` phụ thuộc biến \`factor\`. Nếu bạn thay đổi hoặc \`drop\` khai báo \`factor\`, JShell phải đánh giá lại khả năng biên dịch/liên kết của các đoạn mã liên quan. Vì vậy, trong ứng dụng nhúng, việc quản lý snippet là **quản lý một đồ thị trạng thái và phụ thuộc**, không đơn thuần là gọi \`eval()\` rồi quên mã nguồn.

JShell có API chuẩn ở module \`jdk.jshell\`, gồm:

- \`JShell\`: phiên tương tác, \`eval(String)\`, \`drop(Snippet)\`, \`snippets()\`, \`variables()\`, \`methods()\`, \`types()\`, \`imports()\`, \`status(Snippet)\`.
- \`Snippet\` và các subclass như \`VarSnippet\`, \`MethodSnippet\`, \`TypeDeclSnippet\`, \`ImportSnippet\`.
- \`SnippetEvent\`: thông tin về thay đổi trạng thái sau \`eval\` hoặc \`drop\`.
- \`Snippet.Status\`: trạng thái như \`VALID\`, \`RECOVERABLE_DEFINED\`, \`RECOVERABLE_NOT_DEFINED\`, \`REJECTED\`, \`DROPPED\`, \`OVERWRITTEN\`, \`NONEXISTENT\`.
- \`Diag\`: chẩn đoán các lỗi compiler liên quan đến snippet.

**Điểm quan trọng:** \`eval()\` trả **danh sách** sự kiện. Một lần khai báo lại có thể làm đổi trạng thái nhiều snippet, không chỉ snippet bạn vừa gửi.

## 2. Mô hình phụ thuộc và trạng thái

Ví dụ:

\`\`\`text
VarSnippet: int base = 10
           |
           v
MethodSnippet: int addBase(int x) { return x + base; }
           |
           v
Expression: addBase(5)
\`\`\`

Biểu thức cuối không phải một khai báo lâu dài theo cùng nghĩa với biến/phương thức, nhưng kết quả đánh giá của nó phụ thuộc vào trạng thái phiên tại thời điểm chạy.

Mỗi snippet có một **ID trong phiên**, \`source()\`, \`kind()\` và trạng thái. Một \`SnippetEvent\` có:

| Thuộc tính | Ý nghĩa |
|---|---|
| \`snippet()\` | Snippet chịu tác động |
| \`previousStatus()\` | Trạng thái trước sự kiện; có thể \`null\` cho snippet mới |
| \`status()\` | Trạng thái sau sự kiện |
| \`isSignatureChange()\` | Có thay đổi chữ ký khai báo hay không |
| \`causeSnippet()\` | Snippet khác gây tác động, nếu có |
| \`value()\` | Giá trị chuỗi khi sự kiện có kết quả |
| \`exception()\` | Lỗi thực thi nếu có |

Không nên thiết kế UI chỉ hiển thị “snippet vừa gửi thành công”. Cần xử lý **mọi sự kiện** và cập nhật status cho cả snippet cũ bị ảnh hưởng.

## 3. Các trạng thái cần hiểu

| Status | Diễn giải thực tế |
|---|---|
| \`VALID\` | Snippet được chấp nhận và có thể sử dụng |
| \`RECOVERABLE_DEFINED\` | Khai báo có lỗi phụ thuộc nhưng vẫn có định nghĩa để các khai báo khác có thể tham chiếu trong điều kiện nhất định |
| \`RECOVERABLE_NOT_DEFINED\` | Snippet có thể trở nên hợp lệ khi dependency xuất hiện, nhưng hiện chưa được định nghĩa để thực thi |
| \`REJECTED\` | Snippet bị từ chối; thường là lỗi cú pháp hoặc lỗi biên dịch không thể phục hồi theo cơ chế JShell |
| \`OVERWRITTEN\` | Khai báo đã bị khai báo khác thay thế |
| \`DROPPED\` | Snippet đã bị loại khỏi phiên bằng \`drop\` |
| \`NONEXISTENT\` | Snippet không tồn tại trong phiên hoặc chưa được định nghĩa hợp lệ theo ngữ cảnh API |

Các trạng thái recoverable đặc biệt quan trọng khi người dùng soạn mã theo thứ tự chưa hoàn chỉnh. Ví dụ khai báo phương thức tham chiếu một type chưa có có thể được giữ ở trạng thái phục hồi; khi type được khai báo, JShell có thể tự cập nhật trạng thái.

**Không đồng nhất trạng thái \`VALID\` với “đã chạy thành công mọi logic”**: một khai báo có thể hợp lệ nhưng việc gọi phương thức sau đó vẫn ném exception.

## 4. Khai báo lại: overwrite thay vì xóa mọi snippet

Trong một phiên, bạn có thể nhập lại một biến, phương thức hoặc kiểu phù hợp với quy tắc khai báo lại của JShell:

\`\`\`java
int price = 10;
int price = 20;
\`\`\`

Khai báo mới thay thế phiên bản trước. \`SnippetEvent\` có thể báo khai báo cũ chuyển sang \`OVERWRITTEN\` và khai báo mới trở thành \`VALID\`. Nếu thay đổi chữ ký phương thức hoặc kiểu, các đoạn mã phụ thuộc có thể cần được phân tích lại hoặc chuyển sang trạng thái recoverable.

Hai tình huống khác nhau:

- **Thay giá trị biến:** \`price = 20;\` là một lệnh gán, không phải khai báo lại biến.
- **Khai báo lại biến:** \`int price = 20;\` tạo một phiên bản khai báo mới theo semantics JShell và có thể thay thế snippet cũ.

Với method, JShell cho phép khai báo lại cùng signature. Nếu method mới tham chiếu dependency bị thiếu, các method khác đang dùng nó có thể thay đổi trạng thái. API không bảo đảm giữ nguyên identity của snippet cũ sau overwrite.

Trong ứng dụng nhúng, nên lưu **ID và đối tượng Snippet** đã nhận, thay vì chỉ tra cứu bằng tên. Tên có thể được tái sử dụng qua nhiều vòng khai báo/overwrite, còn các đối tượng snippet phản ánh lịch sử phiên.

## 5. Drop: loại bỏ khai báo có kiểm soát

\`JShell.drop(Snippet)\` yêu cầu xóa một snippet có thể drop trong phiên. Nó trả \`List<SnippetEvent>\` để thông báo cả snippet bị drop lẫn những snippet phụ thuộc bị ảnh hưởng.

Ví dụ thao tác:

\`\`\`java
// Đoạn tích hợp, giả định shell và savedVariable là snippet hợp lệ.
List<SnippetEvent> events = shell.drop(savedVariable);
for (SnippetEvent event : events) {
    System.out.printf("%s: %s -> %s%n",
            event.snippet().id(),
            event.previousStatus(),
            event.status());
}
\`\`\`

Không phải mọi loại snippet đều có cùng khả năng drop; nên lấy đối tượng từ \`shell.variables()\`, \`methods()\`, \`types()\`, \`imports()\` hoặc kết quả của \`eval\` và kiểm tra trạng thái trước khi drop. Nếu snippet đã \`OVERWRITTEN\` hay \`DROPPED\`, không nên giả định thao tác tiếp có cùng tác dụng như trên khai báo đang hoạt động.

**Drop không xóa mọi side effect đã xảy ra.** Ví dụ đoạn mã đã ghi file, gửi HTTP request hoặc sửa một đối tượng Java ngoài phiên JShell thì drop khai báo chỉ thay đổi trạng thái JShell; nó không rollback các tác động bên ngoài.

## 6. Ví dụ Java 17+ hoàn chỉnh: eval, overwrite và drop

Tạo file **\`JShellDependencyDemo.java\`** với nội dung sau (đây là bản cần biên dịch):

\`\`\`java
import jdk.jshell.JShell;
import jdk.jshell.SnippetEvent;
import jdk.jshell.VarSnippet;
import java.util.List;

public class JShellDependencyDemo {
    static void printEvents(String label, List<SnippetEvent> events) {
        System.out.println("-- " + label + " --");
        for (SnippetEvent e : events) {
            String cause = e.causeSnippet() == null
                    ? "-"
                    : e.causeSnippet().id();
            System.out.println(e.snippet().id() + " "
                    + e.previousStatus() + " -> "
                    + e.status() + " cause=" + cause);
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            List<SnippetEvent> first = shell.eval("int base = 10;");
            VarSnippet oldBase = (VarSnippet) first.get(0).snippet();
            printEvents("declare base", first);

            printEvents("declare method",
                    shell.eval("int plusBase(int n) { return n + base; }"));

            printEvents("redeclare base", shell.eval("int base = 20;"));
            System.out.println("old base status: " + shell.status(oldBase));

            VarSnippet current = shell.variables()
                    .filter(v -> v.name().equals("base"))
                    .findFirst()
                    .orElseThrow();

            printEvents("drop base", shell.drop(current));
            System.out.println("current base status: "
                    + shell.status(current));
            System.out.println("method status: "
                    + shell.methods()
                        .filter(m -> m.name().equals("plusBase"))
                        .findFirst()
                        .map(shell::status)
                        .orElse(null));
        }
    }
}
\`\`\`

Biên dịch và chạy trên JDK 17+:

\`\`\`bash
javac --add-modules jdk.jshell JShellDependencyDemo.java
java --add-modules jdk.jshell JShellDependencyDemo
\`\`\`

Các ID và chuỗi sự kiện phụ thuộc thứ tự tạo snippet và thay đổi trạng thái, vì vậy không nên kiểm thử bằng cách hard-code toàn bộ log; các khẳng định cốt lõi cần kiểm tra là:

- khai báo biến ban đầu có trạng thái \`VALID\`;
- sau khi khai báo lại, snippet biến cũ chuyển sang \`OVERWRITTEN\`;
- \`shell.variables()\` trả về khai báo \`base\` hiện còn hoạt động;
- sau \`drop(current)\`, trạng thái biến hiện tại là \`DROPPED\`;
- các khai báo phụ thuộc có thể bị đánh dấu không còn hợp lệ hoặc recoverable.

**Chú ý:** \`shell.methods()\` chỉ liệt kê các method snippet theo API và không tự lọc tất cả trạng thái giống nhau; khi cần chính xác, đọc \`shell.status(m)\` cho từng đối tượng.

## 7. Cách đọc SnippetEvent mà không làm mất tác động lan truyền

Mọi lần \`eval\` hoặc \`drop\` nên xử lý toàn bộ danh sách sự kiện:

\`\`\`java
// Đoạn tích hợp.
List<SnippetEvent> events = shell.eval(source);
for (SnippetEvent event : events) {
    Snippet snippet = event.snippet();
    Snippet.Status current = event.status();
    Snippet.Status previous = event.previousStatus();

    updateUi(snippet.id(), current);
    recordDependencyImpact(event.causeSnippet(), snippet);
}
\`\`\`

\`updateUi\` và \`recordDependencyImpact\` là hàm của ứng dụng, không phải API JShell. \`causeSnippet()\` chỉ ra nguyên nhân khi có; nó không cung cấp toàn bộ đồ thị dependency. Nếu ứng dụng cần đồ thị chính xác, cần thêm phân tích source, metadata hoặc cơ chế truy vết riêng.

Khi gặp \`REJECTED\` hoặc trạng thái không hợp lệ, có thể gọi \`shell.diagnostics(snippet)\` để đọc \`Diag\` có thông tin lỗi. Không dùng riêng \`event.exception()\` để phát hiện lỗi compile: exception phản ánh lỗi thực thi, còn compiler diagnostics có đường riêng.

Ví dụ:

\`\`\`java
// Đoạn tích hợp; events đã được trả về từ eval/drop.
for (SnippetEvent event : events) {
    shell.diagnostics(event.snippet())
            .forEach(diag -> System.err.println(diag.getMessage(null)));
}
\`\`\`

## 8. Quản lý phụ thuộc trong ứng dụng nhúng

Một plugin host thường có nhiều đoạn script do người dùng cung cấp. Có thể tổ chức metadata như:

\`\`\`text
ScriptUnit {
    scriptId
    source
    revision
    declaredDependencies
    activeSnippetIds
}
\`\`\`

Đây là cấu trúc khái niệm, không phải class có sẵn của JShell. Mỗi lần thay đổi một script:

1. Xác định phiên JShell cần thao tác; không trộn snippet giữa các phiên.
2. Kiểm tra nguồn mới, quota và quyền người sửa.
3. Thực hiện \`eval\`, thu thập toàn bộ \`SnippetEvent\`.
4. Cập nhật registry snippet ID, name, status và revision.
5. Kiểm tra các snippet phụ thuộc bị chuyển sang recoverable/rejected.
6. Chỉ công bố script revision mới khi những entry point bắt buộc đều ở trạng thái chấp nhận được.
7. Nếu cần rollback, cân nhắc dựng lại phiên từ **danh sách source đã được phê duyệt**; JShell không cung cấp rollback transaction chung cho mọi side effect.

Một nguyên tắc quan trọng là **không coi mỗi snippet như một artifact có thể tự khôi phục độc lập**. Trạng thái phụ thuộc thuộc về cả phiên.

## 9. Reload và snapshot: cách quản lý thay đổi ổn định hơn

Trong môi trường có yêu cầu reproducibility, thay vì sửa trực tiếp phiên đang phục vụ request, nên áp dụng một cơ chế kiểu staging:

\`\`\`text
Active JShell (revision A)
        |
   snapshot sources
        |
        v
Staging JShell (revision B)
        |
   eval theo thứ tự phụ thuộc
        |
   kiểm tra diagnostics/status
        |
      PASS?
      /   \
    no     yes
    |       |
  hủy B   chuyển request mới sang B
            |
          drain A
            |
          close A
\`\`\`

\`JShell\` không cung cấp sẵn tính năng serialize toàn bộ phiên thành snapshot đáng tin. Host phải quản lý danh sách source, thứ tự replay, dependency và external state. Nếu một script đọc thời gian hiện tại, random, file hoặc network, replay không bảo đảm cùng side effect và kết quả.

Việc giữ hai phiên song song tăng tài nguyên nhưng giúp tách trạng thái kiểm thử khỏi trạng thái đang hoạt động. Khi ứng dụng có hot reload plugin hoặc class loader riêng, cần bảo đảm không để callback/tham chiếu từ phiên cũ tiếp tục sống vô hạn.

## 10. Những giới hạn quan trọng

**Định danh và trạng thái có phạm vi phiên.** Snippet từ JShell A không thể đem \`drop\` trong JShell B như thể chúng cùng lịch sử. IDs chỉ có ý nghĩa trong phiên đã tạo.

**JShell không phải dependency manager cho JAR.** Các dependency của snippet là dependency giữa khai báo/mã Java; việc cung cấp classpath/module path tới phiên là một cơ chế khác, ví dụ thông qua configuration hoặc \`addToClasspath\` theo API tương ứng. Không nhầm lẫn hai lớp dependency.

**Khai báo lại không dọn external state.** Nếu mã tạo thread, mở socket, ghi dữ liệu hoặc đăng ký callback, overwrite/drop không tự gọi \`close\` của các tài nguyên đó.

**Không mặc định thread-safe.** Cần quản lý truy cập đồng thời tới một instance \`JShell\`, tránh nhiều request cùng \`eval\`/drop gây thứ tự bất định. Phân tách phiên theo tenant/user hoặc serialization thao tác tùy nhu cầu.

**JShell không phải sandbox.** Mã Java được thực thi qua JShell có thể gây tác động mạnh tùy môi trường. Với mã không tin cậy, cần cô lập tiến trình, hạn chế filesystem/network và resource quota phù hợp.

## 11. Lỗi phổ biến và checklist

Các lỗi hay gặp:

- Chỉ đọc \`events.get(0)\` sau \`eval\` và bỏ qua sự kiện tác động lên snippet khác.
- Chỉ lưu tên biến/phương thức thay vì lưu ID và status của từng snippet.
- Coi \`OVERWRITTEN\` như \`DROPPED\`; chúng phản ánh hai thao tác khác nhau.
- Drop snippet đang hoạt động rồi kỳ vọng các phương thức phụ thuộc vẫn luôn \`VALID\`.
- Nghĩ khai báo lại biến và gán biến là cùng một hành động.
- Coi \`eval\` thành công về cú pháp là đảm bảo mọi method chạy không lỗi.
- Nhầm \`SnippetEvent.exception()\` với diagnostics của compiler.
- Coi drop/overwrite có khả năng undo tác dụng phụ bên ngoài.
- Dùng một \`JShell\` chung cho mọi tenant không kiểm soát state và quyền.
- Cố tái sử dụng snippet object từ phiên đã close hoặc phiên khác.

Checklist khi xây JShell nhúng:

1. Có registry ánh xạ source/revision → snippet IDs và status?
2. Sau mỗi \`eval\`/\`drop\`, có xử lý **toàn bộ** \`SnippetEvent\`?
3. Có dùng \`diagnostics\` để giải thích trạng thái rejected/recoverable?
4. Có phân biệt khai báo lại, gán giá trị và \`drop\`?
5. Có kiểm soát thứ tự replay và dependency khi dựng lại phiên?
6. Có xử lý lifecycle, resource cleanup và class loader?
7. Có cơ chế staging/rollback ở cấp phiên thay vì kỳ vọng rollback tự động?
8. Có cô lập execution cho mã không đáng tin và đặt quota phù hợp?

**Ghi nhớ:** trong JShell nhúng, snippet là một phần của **trạng thái phiên có phụ thuộc**. \`eval\` và \`drop\` có thể làm thay đổi nhiều snippet; muốn quản lý đúng phải theo dõi \`SnippetEvent\`, \`Snippet.Status\`, version source và vòng đời cả phiên—không chỉ kết quả của một lần gọi.
