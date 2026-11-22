# Tham chiếu vòng

## 1. Tham chiếu vòng là gì?

Trong quá trình phân giải tên (name resolution) của một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **tham chiếu vòng (circular reference)** xuất hiện khi một khai báo phụ thuộc vào chính nó, trực tiếp hoặc thông qua một chuỗi khai báo khác.

Ví dụ, DSL cấu hình có hai hằng:

~~~text
constant A = B + 1
constant B = A + 1
~~~

Muốn tính A, hệ thống cần biết B. Muốn tính B, hệ thống lại cần biết A. Không có giá trị khởi đầu để hoàn tất việc tính toán. Đây là một chu trình phụ thuộc.

Tham chiếu vòng không phải lúc nào cũng sai. Một số ngôn ngữ cho phép hai hàm gọi lẫn nhau, kiểu dữ liệu đệ quy hoặc các module tham chiếu qua lại. Những trường hợp đó có thể hợp lệ nếu ngôn ngữ định nghĩa cách xử lý rõ ràng. Ngược lại, vòng phụ thuộc trong hằng số cần tính ngay, alias kiểu không có điểm dừng hoặc cấu hình khởi tạo có thể khiến quá trình phân giải không thể hoàn tất.

Nhiệm vụ của name resolver không đơn giản là từ chối mọi chu trình. Nó phải:

- Xác định tên nào tham chiếu đến khai báo nào.
- Xây dựng quan hệ phụ thuộc giữa các khai báo.
- Phát hiện các chu trình.
- Phân loại chu trình theo loại khai báo và quy tắc của DSL.
- Chấp nhận các dạng đệ quy được hỗ trợ.
- Từ chối chu trình không hợp lệ với thông báo có thể truy nguyên.

## 2. Phân biệt tham chiếu vòng với tham chiếu tiến và tên chưa được định nghĩa

Một tên được dùng trước khi khai báo chưa chắc là tham chiếu vòng. Cần phân biệt:

| Trường hợp | Ví dụ | Ý nghĩa |
|---|---|---|
| Tham chiếu tiến (forward reference) | A = B + 1, sau đó mới khai báo B | Tên được dùng trước vị trí khai báo |
| Tên chưa được định nghĩa | A = UNKNOWN + 1 | Không có khai báo phù hợp trong phạm vi |
| Tham chiếu vòng trực tiếp | A = A + 1 | Khai báo phụ thuộc vào chính nó |
| Tham chiếu vòng gián tiếp | A = B, B = C, C = A | Một chuỗi phụ thuộc quay lại điểm đầu |
| Đệ quy hợp lệ | Hai hàm gọi lẫn nhau với chữ ký đã biết | Có chu trình nhưng ngôn ngữ cho phép |

Forward reference chỉ mô tả vị trí xuất hiện của tên trong nguồn. DSL có thể cho phép hoặc cấm forward reference độc lập với việc có chu trình hay không.

Ví dụ không có chu trình:

~~~text
constant A = B + 1
constant B = 10
~~~

Nếu DSL cho phép tham chiếu trước, A có thể được tính thành 11. Nếu DSL chỉ cho phép tham chiếu đến khai báo đã xuất hiện, A bị lỗi forward reference dù đồ thị phụ thuộc không có chu trình.

Ví dụ có chu trình:

~~~text
constant A = B + 1
constant B = A + 1
~~~

Đổi thứ tự hai khai báo không giải quyết được phụ thuộc vòng. Đây là vấn đề cấu trúc, không phải vị trí văn bản.

## 3. Tham chiếu vòng xuất hiện ở đâu trong DSL?

Tham chiếu vòng có thể xuất hiện ở nhiều loại khai báo:

- **Hằng số và giá trị cấu hình:** A được tính từ B, còn B được tính từ A.
- **Alias kiểu:** type A = B và type B = A.
- **Kiểu dữ liệu đệ quy:** một record chứa trường có kiểu tham chiếu lại chính record đó.
- **Hàm và rule:** hai hàm hoặc rule gọi lẫn nhau.
- **Module và package:** module A import B, còn B import A.
- **Kế thừa và trait:** một kiểu kế thừa gián tiếp từ chính nó.
- **Biến và biểu thức khởi tạo:** giá trị khởi tạo cần một giá trị chưa được tạo.
- **Workflow và tài nguyên:** hai thành phần cần nhau để khởi tạo hoặc kích hoạt.

Không nên áp dụng một quy tắc chung cho tất cả. Một chu trình trong call graph có thể là đệ quy hợp lệ; một chu trình trong đồ thị khởi tạo hằng số thường không có cách đánh giá hữu hạn nếu không có cơ chế đặc biệt.

## 4. Mô hình hóa phụ thuộc bằng đồ thị

Đồ thị phụ thuộc (dependency graph) là công cụ cơ bản để phân tích tham chiếu vòng:

- Mỗi node đại diện cho một khai báo hoặc một đơn vị cần phân giải.
- Một cạnh có hướng từ A đến B nghĩa là A cần B để hoàn tất một bước cụ thể.
- Một chu trình là đường đi có hướng bắt đầu và kết thúc tại cùng một node.

Ví dụ:

~~~text
constant A = B + 1
constant B = C * 2
constant C = 5
~~~

Đồ thị:

~~~text
A ---> B ---> C
~~~

Không có chu trình. Có thể tính C trước, rồi B, sau đó A.

Với:

~~~text
A = B + 1
B = C * 2
C = A - 3
~~~

Đồ thị:

~~~text
   +--------+
   |        v
   A -----> B
   ^        |
   |        v
   +------- C
~~~

Có chu trình A → B → C → A. Không thể tìm một thứ tự tuyến tính mà mỗi khai báo luôn được xử lý sau tất cả phụ thuộc của nó.

### 4.1 Hướng của cạnh

Trong bài này, cạnh A → B nghĩa là A phụ thuộc vào B. Với quy ước đó, thứ tự xử lý topological sẽ đặt B trước A.

Một số công cụ xây đồ thị theo chiều ngược lại, từ dependency đến dependent. Điều đó không sai, nhưng cần ghi rõ vì nó ảnh hưởng thứ tự duyệt và cách hiển thị chu trình.

### 4.2 Đồ thị có thể có nhiều loại cạnh

Một khai báo có thể phụ thuộc vào khai báo khác vì nhiều lý do:

- Cần kiểu để kiểm tra chữ ký.
- Cần giá trị để tính hằng số.
- Cần module để tra cứu tên.
- Cần đối tượng để khởi tạo.
- Cần kết quả rule để đánh giá rule khác.

Nếu các loại phụ thuộc có quy tắc khác nhau, hãy gắn nhãn cạnh. Ví dụ, tham chiếu đến chữ ký hàm có thể được xử lý trước thân hàm, trong khi phụ thuộc giá trị hằng số cần tính toán thực tế.

## 5. Tham chiếu vòng trực tiếp và gián tiếp

### 5.1 Vòng trực tiếp

~~~text
constant TAX = TAX * 0.1
~~~

Khai báo TAX tham chiếu chính nó. Nếu đây là hằng số cần tính ngay, không có giá trị ban đầu để thực hiện phép nhân.

### 5.2 Vòng gián tiếp

~~~text
constant PRICE = BASE + FEE
constant BASE = PRICE - FEE
constant FEE = 100
~~~

Ta có:

~~~text
PRICE -> BASE -> PRICE
~~~

FEE không nằm trong chu trình. Việc FEE có thể tính được không làm cho PRICE và BASE trở nên hợp lệ.

### 5.3 Nhiều chu trình trong cùng chương trình

~~~text
A = B + 1
B = A + 1

C = D * 2
D = C - 1

E = 10
~~~

Đồ thị có hai thành phần chu trình riêng: {A, B} và {C, D}. E độc lập và vẫn có thể được phân giải. Một resolver tốt nên báo từng chu trình hoặc từng nhóm phụ thuộc vòng thay vì dừng sau lỗi đầu tiên nếu mục tiêu là thu thập diagnostics.

## 6. Phát hiện chu trình bằng DFS

Depth-First Search (DFS) có thể phát hiện chu trình trong đồ thị có hướng bằng cách theo dõi trạng thái của từng node:

- **WHITE / chưa thăm:** node chưa được duyệt.
- **GRAY / đang duyệt:** node đang nằm trên đường đi DFS hiện tại.
- **BLACK / hoàn tất:** node và các phụ thuộc đã được xử lý xong.

Nếu DFS từ A đi đến B, rồi B đi ngược về một node GRAY đang nằm trên stack, cạnh đó tạo chu trình.

### 6.1 Thuật toán khái quát

~~~text
visit(node):
    state[node] = GRAY
    push node onto path

    for each dependency in dependencies(node):
        if state[dependency] == WHITE:
            visit(dependency)
        else if state[dependency] == GRAY:
            report cycle from dependency to node

    pop node from path
    state[node] = BLACK
~~~

Khi gặp node GRAY, resolver có thể dùng stack để dựng đường đi gây chu trình. Ví dụ:

~~~text
path = [A, B, C]
next dependency = A
~~~

Diagnostics có thể chỉ ra:

~~~text
Circular dependency detected:
A -> B -> C -> A
~~~

### 6.2 Vì sao node BLACK không phải chu trình?

Một cạnh đến node BLACK có nghĩa node đó đã được xử lý xong trong một nhánh trước. Nó không nằm trên đường đi hiện tại, nên cạnh này không tạo chu trình mới.

Phân biệt GRAY và BLACK là điều quan trọng. Nếu chỉ dùng một cờ visited, thuật toán có thể nhầm một dependency được chia sẻ bởi nhiều khai báo thành chu trình.

### 6.3 Độ phức tạp

Với danh sách kề, DFS duyệt mỗi node và cạnh một số lần hằng định:

\[
O(V + E)
\]

Trong đó V là số khai báo và E là số quan hệ phụ thuộc. Đây là độ phức tạp phù hợp cho phần lớn đồ thị khai báo trong DSL.

## 7. Ví dụ phát hiện vòng bằng Java

Một mô hình đơn giản có thể lưu tên khai báo và danh sách phụ thuộc:

~~~java
enum VisitState {
    WHITE,
    GRAY,
    BLACK
}

final class DependencyGraph {
    private final Map<String, List<String>> edges = new LinkedHashMap<>();

    void addNode(String name) {
        edges.computeIfAbsent(name, ignored -> new ArrayList<>());
    }

    void addDependency(String name, String dependency) {
        addNode(name);
        addNode(dependency);
        edges.get(name).add(dependency);
    }

    Map<String, List<String>> edges() {
        return edges;
    }
}
~~~

DFS có thể trả về đường đi chu trình đầu tiên:

~~~java
final class CycleDetector {
    private final Map<String, VisitState> states = new HashMap<>();
    private final Deque<String> path = new ArrayDeque<>();
    private List<String> cycle;

    Optional<List<String>> findCycle(DependencyGraph graph) {
        for (String node : graph.edges().keySet()) {
            states.put(node, VisitState.WHITE);
        }

        for (String node : graph.edges().keySet()) {
            if (states.get(node) == VisitState.WHITE && visit(node, graph)) {
                return Optional.of(List.copyOf(cycle));
            }
        }
        return Optional.empty();
    }

    private boolean visit(String node, DependencyGraph graph) {
        states.put(node, VisitState.GRAY);
        path.addLast(node);

        for (String dependency : graph.edges().get(node)) {
            VisitState state = states.get(dependency);

            if (state == VisitState.GRAY) {
                cycle = extractCycle(dependency);
                return true;
            }

            if (state == VisitState.WHITE && visit(dependency, graph)) {
                return true;
            }
        }

        path.removeLast();
        states.put(node, VisitState.BLACK);
        return false;
    }

    private List<String> extractCycle(String repeated) {
        List<String> result = new ArrayList<>();
        boolean collecting = false;

        for (String item : path) {
            if (item.equals(repeated)) {
                collecting = true;
            }
            if (collecting) {
                result.add(item);
            }
        }

        result.add(repeated);
        return result;
    }
}
~~~

Đây là mã minh họa cho việc tìm một chu trình đầu tiên trong đồ thị đã được xây dựng. Trong triển khai thực tế, cần xử lý thêm:

- Node chưa có danh sách cạnh.
- Cạnh trùng lặp.
- Nhiều chu trình.
- Vòng tự tham chiếu A → A.
- Vị trí nguồn của từng cạnh.
- Giới hạn độ sâu hoặc stack khi đầu vào rất lớn.

Không nên dùng trực tiếp tên chuỗi làm định danh nếu DSL hỗ trợ scope lồng nhau hoặc cùng tên ở nhiều module. Khi đó, node nên dùng SymbolId duy nhất và giữ tên hiển thị riêng.

## 8. Phát hiện nhóm phụ thuộc mạnh liên thông (SCC)

DFS ba màu thường tìm một chu trình hoặc phát hiện có chu trình. Nếu cần phân loại tất cả nhóm khai báo có thể đi đến nhau, có thể dùng **Strongly Connected Components (SCC)**.

Một thành phần liên thông mạnh là tập node mà từ mỗi node có đường đi đến mọi node khác trong cùng tập.

Ví dụ:

~~~text
A -> B
B -> C
C -> A
C -> D
D -> E
E -> D
~~~

Các SCC:

- {A, B, C}
- {D, E}

Hai nhóm này là hai vùng chu trình riêng. Cạnh C → D nối hai nhóm nhưng không gộp chúng thành một SCC vì không có đường đi ngược từ D về C.

### 8.1 Tarjan và Kosaraju

Hai thuật toán phổ biến:

- **Tarjan:** dùng DFS, discovery index và low-link value để tìm SCC trong O(V + E).
- **Kosaraju:** DFS trên đồ thị gốc và đồ thị đảo cạnh, cũng có độ phức tạp O(V + E).

Sau khi có SCC:

- Thành phần có nhiều hơn một node chắc chắn chứa chu trình.
- Thành phần chỉ có một node vẫn chứa chu trình nếu node có self-edge.

SCC hữu ích khi compiler muốn báo mọi nhóm phụ thuộc vòng trong một lần phân tích, thay vì chỉ dừng ở chu trình đầu tiên.

## 9. Sắp xếp phụ thuộc bằng topological sort

Nếu đồ thị không có chu trình, có thể tìm thứ tự xử lý sao cho mọi dependency được xử lý trước khai báo phụ thuộc vào nó.

Với quy ước cạnh A → B nghĩa là A phụ thuộc vào B, thứ tự cần có B trước A.

Ví dụ:

~~~text
A -> B
A -> C
B -> D
C -> D
~~~

Một thứ tự hợp lệ:

~~~text
D, B, C, A
~~~

Hoặc:

~~~text
D, C, B, A
~~~

Có thể có nhiều thứ tự hợp lệ. Điều quan trọng là mọi dependency phải đứng trước dependent.

### 9.1 Kahn's algorithm

Một cách sắp xếp là dùng indegree trên đồ thị đã đảo theo hướng dependency → dependent:

1. Tính số dependency còn chưa xử lý của mỗi node.
2. Đưa các node có số dependency bằng 0 vào hàng đợi.
3. Lấy một node ra, đánh dấu hoàn tất.
4. Giảm số dependency còn lại của các node phụ thuộc vào nó.
5. Đưa node vừa đạt 0 vào hàng đợi.
6. Nếu số node đã xử lý nhỏ hơn tổng số node, phần còn lại chứa chu trình.

Độ phức tạp là O(V + E) với hàng đợi phù hợp.

### 9.2 Khi nào topological sort hữu ích?

- Tính hằng số và giá trị cấu hình.
- Nạp module theo thứ tự phụ thuộc.
- Khởi tạo tài nguyên.
- Sinh mã theo thứ tự khai báo.
- Chạy các bước build hoặc workflow có dependency.

Topological sort chỉ áp dụng cho phần quan hệ cần thứ tự tuyến tính. Một nhóm đệ quy hợp lệ có thể cần được gom thành một đơn vị xử lý hoặc phân tích bằng cơ chế riêng.

## 10. Không phải mọi chu trình đều không hợp lệ

Resolver phải hiểu loại khai báo để quyết định chu trình nào được chấp nhận.

### 10.1 Hàm gọi đệ quy và gọi lẫn nhau

~~~text
function is_even(n: Integer): Boolean
  if n == 0 then true
  else is_odd(n - 1)

function is_odd(n: Integer): Boolean
  if n == 0 then false
  else is_even(n - 1)
~~~

Hai hàm phụ thuộc lẫn nhau qua lời gọi. Nếu DSL cho phép forward declaration hoặc thu thập chữ ký trước khi phân tích thân hàm, chu trình này có thể hợp lệ.

Resolver cần phân biệt:

- Phân giải tên hàm.
- Kiểm tra chữ ký và kiểu tham số.
- Kiểm tra thân hàm.
- Đánh giá hoặc thực thi lời gọi.

Có thể resolve tên và chữ ký của cả hai hàm trước, sau đó mới kiểm tra thân. Việc có thể gọi lẫn nhau không có nghĩa chương trình chắc chắn kết thúc; termination là một vấn đề riêng.

### 10.2 Kiểu dữ liệu đệ quy

~~~text
type Node {
  value: Integer
  next: Node?
}
~~~

Đây là kiểu đệ quy hợp lệ trong nhiều hệ kiểu vì trường next là một tham chiếu có thể vắng mặt. Cấu trúc dữ liệu hữu hạn có thể kết thúc ở null.

Một kiểu alias thuần:

~~~text
type A = B
type B = A
~~~

thường không hợp lệ vì A và B chỉ định nghĩa vòng quanh nhau mà không tạo ra cấu trúc cụ thể.

Ngôn ngữ cần quy định loại tham chiếu nào cho phép recursion: record, class, pointer, reference, collection hoặc function type. Không nên suy ra rằng mọi chu trình type đều hợp lệ.

### 10.3 Module import vòng

~~~text
module A imports B
module B imports A
~~~

Một số ngôn ngữ cho phép module import vòng nếu việc nạp được chia giai đoạn và các khai báo cần thiết có thể được đăng ký trước. Một số ngôn ngữ cấm vì khởi tạo module sẽ phụ thuộc vòng.

Ngay cả khi import vòng được phép, thứ tự khởi tạo biến toàn cục vẫn có thể tạo lỗi. Cần tách dependency về tên/chữ ký khỏi dependency về giá trị khởi tạo.

### 10.4 Rule tham chiếu lẫn nhau

Trong rule engine, hai rule có thể kích hoạt hoặc tham chiếu kết quả của nhau. Điều này có thể tạo vòng đánh giá lặp lại. Hệ thống cần có semantics rõ như:

- Chỉ đánh giá một lượt theo thứ tự cố định.
- Lặp đến khi đạt trạng thái ổn định (fixed point).
- Giới hạn số vòng.
- Phát hiện trạng thái lặp.
- Từ chối dependency cycle.

Nếu không có quy tắc dừng, runtime có thể chạy vô hạn.

## 11. Phân biệt chu trình phân giải tên với chu trình thực thi

Hai loại chu trình có liên hệ nhưng không đồng nhất.

**Chu trình phân giải tên** xuất hiện khi resolver không thể xác định hoặc hoàn tất một khai báo do các dependency quay lại nhau. Ví dụ, alias A = B và B = A.

**Chu trình thực thi** xuất hiện khi chương trình chạy lặp lại một chuỗi lời gọi hoặc workflow. Ví dụ, hàm A gọi B và B gọi A.

Một chu trình trong call graph có thể hợp lệ nếu có điều kiện dừng. Một chu trình trong đồ thị tính giá trị hằng số có thể không hợp lệ vì không có giá trị khởi đầu.

Vì vậy, không nên dùng một bộ phát hiện chu trình duy nhất rồi từ chối mọi loại vòng. Cần xây đồ thị đúng với giai đoạn và loại phụ thuộc đang xét.

## 12. Quy trình phân giải tên có kiểm soát chu trình

Một resolver cho DSL có thể chia thành nhiều giai đoạn:

### Giai đoạn 1: Thu thập khai báo

Đọc các khai báo và tạo symbol table cho từng scope hoặc module. Ở bước này, resolver ghi nhận tên, loại symbol, vị trí nguồn và phạm vi.

### Giai đoạn 2: Đăng ký chữ ký

Đăng ký chữ ký hàm, kiểu, rule hoặc khai báo có thể tham chiếu trước. Việc này cho phép phân giải forward reference hợp lệ mà không cần tính ngay mọi giá trị.

### Giai đoạn 3: Phân giải tên

Mỗi identifier được ánh xạ đến một SymbolId. Nếu không tìm thấy tên phù hợp, tạo diagnostic undefined name. Nếu có nhiều ứng viên, xử lý ambiguity theo quy tắc scope và import.

### Giai đoạn 4: Xây dependency graph

Từ các tham chiếu đã phân giải, tạo cạnh có nhãn biểu diễn loại phụ thuộc. Không nên xây đồ thị chỉ từ chuỗi tên trước khi biết scope, vì cùng một tên có thể chỉ đến các symbol khác nhau.

### Giai đoạn 5: Phân loại chu trình

Tìm self-reference, cycle và SCC. Với mỗi nhóm, xác định loại khai báo và quy tắc cho phép recursion.

### Giai đoạn 6: Xử lý theo loại

- Hằng số: thường yêu cầu đồ thị không chu trình trước khi tính.
- Hàm: có thể cho phép mutual recursion nếu chữ ký đã được đăng ký.
- Kiểu: cho phép recursive type theo quy tắc biểu diễn.
- Module: áp dụng chính sách import và initialization.
- Rule/workflow: dùng chính sách cycle hoặc fixed-point riêng nếu được hỗ trợ.

### Giai đoạn 7: Kiểm tra kiểu và giá trị

Sau khi tên được liên kết, kiểm tra kiểu, phạm vi, giá trị hằng và các ràng buộc ngữ nghĩa.

### Giai đoạn 8: Lập thứ tự thực thi hoặc đánh giá

Với đồ thị không chu trình, topological sort tạo thứ tự xử lý. Với nhóm đệ quy hợp lệ, chuyển cho cơ chế chuyên biệt.

~~~text
Source declarations
        |
        v
Collect symbols
        |
        v
Resolve names
        |
        v
Build dependency graph
        |
        v
Detect cycles / SCC
        |
        +---- invalid cycle ---> diagnostics
        |
        +---- allowed recursion
        |          |
        |          v
        |     recursive resolver
        |
        v
Topological order for acyclic dependencies
        |
        v
Type checking / evaluation / initialization
~~~

## 13. Cách xử lý chu trình không hợp lệ

Khi phát hiện chu trình không được phép, resolver nên báo lỗi sớm và đủ thông tin để người viết sửa.

Ví dụ:

~~~text
constant A = B + 1
constant B = C + 1
constant C = A + 1
~~~

Thông báo tốt:

~~~text
Circular constant dependency:
A -> B -> C -> A

A depends on B at config.dsl:1:13
B depends on C at config.dsl:2:13
C depends on A at config.dsl:3:13
~~~

Thông báo chỉ nói "circular reference" sẽ khó xử lý nếu chương trình có hàng trăm khai báo.

### 13.1 Thông tin nên có trong diagnostic

- Mã lỗi ổn định, ví dụ DSL_CIRCULAR_DEPENDENCY.
- Loại khai báo tạo chu trình.
- Đường đi chu trình.
- Vị trí nguồn của từng cạnh phụ thuộc.
- Vị trí khai báo đầu tiên trong chu trình.
- Gợi ý cách tách hoặc thay đổi dependency nếu xác định được.

### 13.2 Chọn vị trí lỗi chính

Có thể đánh dấu cạnh đóng chu trình hoặc khai báo mà resolver đang xử lý khi phát hiện vòng. Nhưng nên cung cấp cả đường đi để người dùng hiểu toàn bộ nhóm liên quan.

### 13.3 Tránh báo lỗi dây chuyền

Nếu A, B và C cùng nằm trong một SCC không hợp lệ, việc đánh dấu từng symbol là unresolved có thể tạo hàng loạt lỗi phụ. Có thể tạo một diagnostic chính cho SCC và đánh dấu các khai báo thành viên là invalid because of cycle để ngăn lỗi thứ cấp không hữu ích.

## 14. Một số chiến lược xử lý phụ thuộc vòng

### 14.1 Cấm chu trình và yêu cầu đồ thị DAG

Đây là chiến lược đơn giản cho hằng số, biến cấu hình và các bước khởi tạo cần thứ tự.

Ưu điểm:

- Dễ hiểu và dễ kiểm tra.
- Có thể dùng topological sort.
- Kết quả dễ tái lập.

Hạn chế:

- Không hỗ trợ mutual recursion hoặc recursive definitions.
- Người dùng có thể phải tách khai báo hoặc viết lại mô hình.

### 14.2 Khai báo trước, định nghĩa sau

Với hàm hoặc kiểu, có thể đăng ký tên và chữ ký trước khi phân tích thân:

~~~text
declare function is_even(Integer): Boolean
declare function is_odd(Integer): Boolean

define function is_even(n)
  if n == 0 then true else is_odd(n - 1)

define function is_odd(n)
  if n == 0 then false else is_even(n - 1)
~~~

Khi thân is_even tham chiếu is_odd, symbol và chữ ký của is_odd đã tồn tại. Đây là cách phổ biến để hỗ trợ mutual recursion.

### 14.3 Lazy evaluation

Thay vì tính một giá trị ngay khi gặp khai báo, runtime có thể trì hoãn cho đến khi giá trị được sử dụng.

~~~text
lazy constant A = expensive_expression
~~~

Lazy evaluation có thể tránh tính những giá trị không cần thiết, nhưng không tự giải quyết mọi chu trình. Nếu A cần B và B cần A, lần truy cập đầu tiên vẫn có thể quay vòng.

Runtime cần phát hiện trạng thái đang tính (evaluating) để báo circular evaluation hoặc áp dụng semantics đệ quy được định nghĩa.

### 14.4 Fixed-point semantics

Một số hệ thống rule hoặc phân tích dữ liệu có thể định nghĩa chu trình bằng cách lặp đến khi đạt điểm bất động (fixed point).

Ví dụ, một tập quan hệ được mở rộng dần cho đến khi không thêm được phần tử mới:

~~~text
repeat
  new_values = evaluate_rules(current_values)
  changed = new_values != current_values
  current_values = new_values
until not changed
~~~

Cách này chỉ có thể kết thúc nếu có điều kiện phù hợp, chẳng hạn miền giá trị hữu hạn và phép mở rộng đơn điệu. Nếu không, cần giới hạn vòng lặp hoặc cơ chế phát hiện không hội tụ.

Không nên tự áp dụng fixed point cho hằng số thông thường. Đây là một semantics riêng cần được DSL công bố.

### 14.5 Dependency injection hoặc tách trách nhiệm

Đôi khi vòng phụ thuộc cho thấy mô hình khai báo bị kết hợp quá chặt:

~~~text
Pricing depends on Tax
Tax depends on Pricing
~~~

Có thể tách phần dữ liệu chung hoặc tạo một abstraction thứ ba mà cả hai cùng phụ thuộc. Tuy nhiên, chỉ nên làm khi quan hệ miền thực sự có thể phân rã; không nên thay đổi mô hình nghiệp vụ chỉ để làm đồ thị hết chu trình.

## 15. Chu trình trong hệ kiểu

Type resolver cần phân biệt alias trong suốt và kiểu có cấu trúc tham chiếu lại chính nó.

### 15.1 Alias vòng không có cấu trúc cơ sở

~~~text
type A = B
type B = C
type C = A
~~~

Nếu alias chỉ thay thế tên bằng kiểu khác, chu trình này không tạo ra kiểu cụ thể. Resolver nên báo lỗi alias cycle.

### 15.2 Recursive record

~~~text
type Tree {
  value: Integer
  children: List<Tree>
}
~~~

Kiểu Tree tham chiếu lại Tree thông qua một cấu trúc List. Nếu hệ kiểu hỗ trợ recursive record, đây là một định nghĩa hợp lệ.

### 15.3 Indirection và kích thước kiểu

Một số ngôn ngữ yêu cầu recursive type đi qua một lớp indirection như reference, pointer hoặc collection. Lý do có thể liên quan đến việc tính kích thước kiểu.

Ví dụ, một record chứa trực tiếp chính nó theo giá trị:

~~~text
type Node {
  next: Node
}
~~~

có thể tạo kích thước vô hạn nếu không có indirection. Nhưng:

~~~text
type Node {
  next: Node?
}
~~~

có thể hợp lệ nếu nullable reference có kích thước cố định. Quy tắc cụ thể tùy mô hình kiểu của DSL.

### 15.4 Recursive type và type checking

Type checker có thể cần:

- Đăng ký type symbol trước khi resolve field.
- Theo dõi type đang được resolve.
- Phân biệt chu trình được phép qua indirection với alias cycle.
- Xây type graph hoặc type constructor.
- Tránh đệ quy vô hạn khi so sánh hai kiểu đệ quy.

Khi so sánh recursive types, một thuật toán có thể ghi nhận cặp kiểu đã kiểm tra để không lặp lại cùng một cặp vô hạn.

## 16. Chu trình trong module và khởi tạo

Module có thể phụ thuộc lẫn nhau ở hai cấp độ khác nhau:

1. **Compile-time dependency:** cần module khác để tìm kiểu, hàm hoặc khai báo.
2. **Initialization dependency:** cần giá trị hoặc trạng thái runtime của module khác khi khởi tạo.

Một ngôn ngữ có thể cho phép vòng import ở cấp compile-time nhưng cấm vòng khởi tạo.

Ví dụ:

~~~text
module A
  import B
  let a = B.value

module B
  import A
  let value = A.a + 1
~~~

Nếu A.a cần B.value và B.value lại cần A.a, initialization cycle xuất hiện. Resolver có thể phân giải được cả hai tên nhưng runtime không thể khởi tạo giá trị theo thứ tự thông thường.

Cần xác định:

- Module được nạp theo thứ tự nào?
- Các symbol có được đăng ký trước khi khởi tạo không?
- Global initializer có được phép tham chiếu module khác không?
- Có lazy initialization không?
- Nếu truy cập một giá trị đang khởi tạo thì lỗi gì xảy ra?

Không nên coi việc import thành công là bằng chứng rằng khởi tạo module chắc chắn hợp lệ.

## 17. Scope, shadowing và tham chiếu vòng

Name resolver phải xây dependency graph sau khi xác định đúng symbol. Cùng một tên ở các scope khác nhau có thể tham chiếu đến các khai báo khác nhau.

Ví dụ:

~~~text
let rate = 5

scope {
  let rate = 10
  let total = rate * 2
}
~~~

Trong scope bên trong, total phụ thuộc vào rate nội bộ có giá trị 10, không phải rate bên ngoài. Nếu đồ thị chỉ dùng chuỗi rate, resolver có thể tạo dependency sai.

### 17.1 Dùng SymbolId thay cho tên hiển thị

Mỗi khai báo sau khi thu thập nên có định danh duy nhất:

~~~text
SymbolId: moduleA.scope1.rate
SymbolId: moduleA.scope2.rate
~~~

Các cạnh dependency trỏ đến SymbolId. Tên hiển thị vẫn được giữ để tạo diagnostics.

### 17.2 Import và alias

Nếu module import một tên dưới alias, resolver phải liên kết alias với symbol gốc:

~~~text
import pricing.discount as discount_rule
~~~

Tham chiếu discount_rule và pricing.discount có thể cùng trỏ đến một symbol. Không nên tạo hai node dependency cho cùng một khai báo chỉ vì có hai tên truy cập.

### 17.3 Shadowing không tự tạo chu trình

Một khai báo nội bộ cùng tên với khai báo bên ngoài không nhất thiết tham chiếu chính nó. Quy tắc scope xác định tên nào được chọn. Chu trình chỉ được xác định sau khi name binding hoàn tất.

## 18. Tái phân giải khi có thay đổi

Trong IDE hoặc hệ thống cấu hình động, người dùng có thể sửa một khai báo sau khi resolver đã xây dependency graph.

Ví dụ ban đầu:

~~~text
A = B + 1
B = 10
~~~

Sau khi sửa B:

~~~text
B = A + 1
~~~

Đồ thị trước đó không có chu trình; đồ thị mới có A ↔ B.

Nếu hệ thống hỗ trợ incremental resolution, cần xác định:

- Những node nào bị ảnh hưởng khi một khai báo đổi.
- Cạnh dependency cũ nào cần xóa.
- Các dependency mới nào cần thêm.
- SCC nào cần tính lại.
- Kết quả đã cache nào phải vô hiệu hóa.
- Diagnostics cũ nào cần xóa hoặc cập nhật.

Một cách đơn giản là xây lại toàn bộ đồ thị khi file thay đổi. Với dự án lớn, có thể cập nhật theo vùng phụ thuộc, nhưng cần bảo đảm không giữ cạnh cũ gây báo lỗi sai.

## 19. Kiểm thử tham chiếu vòng

Nên kiểm thử riêng thuật toán đồ thị và ngữ nghĩa của từng loại khai báo.

### 19.1 Các trường hợp đồ thị cơ bản

| Đồ thị | Kết quả mong đợi |
|---|---|
| A → B, B không có dependency | Không có chu trình |
| A → A | Vòng trực tiếp |
| A → B, B → A | Vòng hai node |
| A → B → C → A | Vòng nhiều node |
| A → B, C → B | Không có chu trình chỉ vì chia sẻ dependency |
| A → B → C, D → E | Hai nhánh độc lập, không chu trình |
| Hai SCC riêng | Phát hiện đúng từng nhóm |

### 19.2 Kiểm thử phân loại theo loại khai báo

- Hằng số tự tham chiếu phải bị từ chối nếu không có semantics đệ quy.
- Hai hằng số phụ thuộc lẫn nhau phải bị phát hiện.
- Hàm gọi lẫn nhau được chấp nhận nếu DSL hỗ trợ mutual recursion.
- Alias kiểu vòng phải bị từ chối nếu alias trong suốt.
- Recursive record hợp lệ phải được chấp nhận theo quy tắc type system.
- Module import vòng và module initialization vòng phải được phân biệt.

### 19.3 Kiểm thử diagnostics

Xác nhận:

- Đường đi chu trình đúng.
- Mọi cạnh có vị trí nguồn.
- Tên hiển thị đúng scope.
- Một SCC không tạo hàng loạt lỗi thứ cấp khó hiểu.
- Diagnostic ổn định khi thứ tự duyệt thay đổi.

### 19.4 Kiểm thử quy mô

Với đồ thị lớn, kiểm tra:

- Thời gian phát hiện chu trình.
- Bộ nhớ của adjacency list và stack.
- Đồ thị sâu có gây tràn stack DFS đệ quy không.
- Nhiều dependency trùng có làm tăng công việc không cần thiết không.

Nếu đồ thị có thể sâu hàng chục nghìn node, cân nhắc DFS iterative hoặc giới hạn kích thước đầu vào.

## 20. Những sai lầm thường gặp

### Từ chối mọi chu trình

Điều này có thể loại bỏ cả mutual recursion hoặc recursive type hợp lệ.

**Cách khắc phục:** phân loại cạnh và loại khai báo; định nghĩa rõ loại recursion được phép.

### Chỉ kiểm tra tên xuất hiện trước hay sau

Forward reference không đồng nghĩa với circular reference. Đổi thứ tự khai báo không sửa được một chu trình thực sự.

**Cách khắc phục:** xây dependency graph từ symbol đã phân giải.

### Dùng tên văn bản làm node

Hai scope có thể có cùng tên nhưng là hai symbol khác nhau.

**Cách khắc phục:** dùng SymbolId duy nhất và giữ source location.

### Chỉ dùng một cờ visited

Một node được thăm từ nhánh khác có thể bị nhầm là chu trình.

**Cách khắc phục:** dùng trạng thái WHITE/GRAY/BLACK hoặc thuật toán SCC.

### Phát hiện chu trình quá muộn

Nếu đợi đến lúc đánh giá từng giá trị mới phát hiện vòng, lỗi khó truy nguyên và có thể gây đệ quy vô hạn.

**Cách khắc phục:** phân tích dependency graph trước khi tính các khai báo cần thứ tự.

### Nhầm call cycle với constant cycle

Hàm gọi lẫn nhau có thể hợp lệ; hằng số tính lẫn nhau thường không có điểm khởi đầu.

**Cách khắc phục:** tạo dependency graph riêng cho từng loại ngữ nghĩa hoặc gắn nhãn cạnh.

### Báo lỗi không có đường đi

Thông báo chung chung không giúp người dùng biết phải sửa khai báo nào.

**Cách khắc phục:** báo chu trình, vị trí của các tham chiếu và loại dependency.

## 21. Quy trình thiết kế hỗ trợ tham chiếu vòng

Khi xây dựng name resolver cho DSL, có thể thực hiện:

1. **Xác định loại khai báo:** hằng số, hàm, kiểu, module, rule hay cấu hình.
2. **Định nghĩa chính sách recursion:** loại nào cấm, loại nào cho phép và điều kiện đi kèm.
3. **Thu thập symbol:** tạo SymbolId và scope trước khi phân tích dependency.
4. **Resolve tên:** liên kết từng identifier với symbol chính xác.
5. **Ghi nhận dependency:** tạo cạnh có loại và source span.
6. **Phân tích đồ thị:** dùng DFS, SCC hoặc topological sort phù hợp.
7. **Phân loại chu trình:** tách chu trình không hợp lệ khỏi recursion được hỗ trợ.
8. **Xử lý theo giai đoạn:** đăng ký chữ ký, resolve thân, tính giá trị hoặc khởi tạo.
9. **Tạo diagnostics:** nêu đường đi, vị trí và cách khắc phục.
10. **Kiểm thử:** bao phủ vòng trực tiếp, gián tiếp, nhiều SCC, scope và loại khai báo.

Với DSL nhỏ, DFS có thể đủ. Với compiler hoặc cấu hình lớn cần báo nhiều nhóm lỗi, SCC và đồ thị có nhãn sẽ hữu ích hơn.

## 22. Ví dụ tổng hợp

Giả sử DSL có ba loại khai báo: hằng số, hàm và kiểu:

~~~text
constant BASE_PRICE = TAXED_PRICE - TAX
constant TAXED_PRICE = BASE_PRICE + TAX
constant TAX = 100

function is_even(n: Integer): Boolean
  if n == 0 then true else is_odd(n - 1)

function is_odd(n: Integer): Boolean
  if n == 0 then false else is_even(n - 1)

type Tree {
  value: Integer
  children: List<Tree>
}
~~~

Resolver cần xử lý khác nhau:

- BASE_PRICE và TAXED_PRICE tạo chu trình hằng số, cần báo lỗi nếu hằng số phải tính ngay.
- TAX không nằm trong chu trình và có thể phân giải độc lập.
- is_even và is_odd gọi lẫn nhau; có thể hợp lệ nếu chữ ký được đăng ký trước và mutual recursion được hỗ trợ.
- Tree là recursive type; có thể hợp lệ vì cấu trúc List tạo indirection theo quy tắc type system.

Ví dụ này cho thấy một chương trình có thể đồng thời chứa chu trình hợp lệ và không hợp lệ. Phân tích theo loại khai báo giúp resolver đưa ra quyết định chính xác hơn.

## 23. Câu hỏi tự kiểm tra

1. Phân biệt forward reference, undefined name và circular reference.
2. Đồ thị dependency biểu diễn điều gì và cạnh A → B có thể được hiểu như thế nào?
3. Phân biệt vòng trực tiếp và vòng gián tiếp.
4. DFS dùng trạng thái WHITE, GRAY và BLACK để phát hiện chu trình ra sao?
5. Vì sao SCC hữu ích khi cần báo nhiều nhóm phụ thuộc vòng?
6. Topological sort có thể dùng trong giai đoạn nào của resolver?
7. Vì sao mutual recursion giữa các hàm có thể hợp lệ?
8. Phân biệt alias type cycle với recursive record.
9. Vì sao import cycle khác initialization cycle?
10. Vì sao dependency graph nên dùng SymbolId thay vì tên văn bản?
11. Lazy evaluation có tự động giải quyết circular dependency không?
12. Khi nào fixed-point evaluation có thể là một semantics phù hợp?
13. Một diagnostic tốt cho circular reference cần chứa thông tin nào?
14. Làm thế nào để tái phân giải dependency khi một khai báo thay đổi?

Tham chiếu vòng cần được phân tích theo loại dependency và giai đoạn xử lý. Khi resolver liên kết đúng symbol, xây đồ thị có hướng, phát hiện chu trình và áp dụng chính sách recursion rõ ràng, DSL có thể hỗ trợ những dạng đệ quy hợp lệ đồng thời từ chối các vòng phụ thuộc không thể giải quyết.
