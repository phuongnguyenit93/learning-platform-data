Bạn sẽ xác định những tính năng được chuẩn hóa ở Java 21 vẫn là API ổn định trên JDK hiện đại bằng phương pháp nào?
Bạn phân biệt tính năng mới của Java 21 với tính năng đã được giới thiệu ở Java trước đó nhưng tương tác tốt với Java 21 ra sao?
Bạn sẽ xác minh tính năng Java 21 đã ở trạng thái final thay vì preview khi lựa chọn cho production như thế nào?
Bạn mô tả sự khác biệt giữa source compatibility, binary compatibility và runtime behavior khi nâng ứng dụng lên Java 21 như thế nào?
Bạn sẽ sử dụng javac --release 21 để kiểm tra cú pháp và public API thuộc mức nền tảng Java 21 ra sao?
Bạn phân biệt việc chạy chương trình xây bằng Java 21 trên một JDK mới và cố chạy bytecode của nó trên JDK cũ ra sao?
Bạn sẽ phát hiện dependency được biên dịch cho class file version cao hơn runtime hỗ trợ bằng những công cụ nào?
Bạn phân tích vì sao project cần cấu hình đồng nhất Java toolchain trong IDE, Maven hoặc Gradle và CI như thế nào?
Bạn sẽ lập tiêu chí chọn record patterns, pattern switch, Sequenced Collections và virtual threads cho một service hiện có ra sao?
Bạn mô tả vai trò của bộ regression tests khi nâng từ Java 17 lên Java 21 dù code không dùng cú pháp mới như thế nào?
Bạn sẽ xem release notes và JEP để đối chiếu một hành vi JVM thay đổi theo bản JDK như thế nào?
Bạn phân tích vì sao không nên mang nguyên cấu hình các preview features từng xuất hiện trong Java 21 sang JDK mới ra sao?
Bạn sẽ xác định vì sao một ứng dụng chạy được trên JDK 21 vẫn có thể lỗi khi thay đổi thư viện bytecode hoặc serializer như thế nào?
Bạn phân biệt khả năng tương thích API với mức hỗ trợ của một framework đối với record patterns hoặc virtual threads ra sao?
Bạn sẽ xây bộ smoke tests đại diện cho đồng thời, collection ordering, serialization và GC khi nâng JDK như thế nào?
Bạn mô tả vì sao triển khai Java 21 LTS không đồng nghĩa mọi cờ JVM có cùng hành vi trên JDK hiện đại hơn như thế nào?
Bạn sẽ dùng JMH để đo một microbenchmark về pattern matching nhưng vẫn đánh giá readability và bảo trì trước khi refactoring như thế nào?
Bạn phân tích khi nào nên để code mới dùng Java 21 nhưng thư viện công khai vẫn build target thấp hơn như thế nào?
Bạn sẽ kiểm tra dependency và runtime image có đủ các Java modules cần thiết sau nâng JDK như thế nào?
Bạn mô tả cách dùng JFR, logs và test metrics để thiết lập baseline trước một đợt Java 21 migration ra sao?
Bạn sẽ kiểm tra khác biệt về Unicode, locale hoặc TLS behavior khi chạy lại ứng dụng trên JDK khác như thế nào?
Bạn phân tích vì sao cần tài liệu hóa sự khác nhau giữa Java 21 semantics và các cải tiến có từ JDK sau này ra sao?
Bạn giải thích record patterns được hoàn thiện ở Java 21 mở rộng record matching so với type pattern cho instanceof như thế nào?
Bạn sẽ dùng record pattern để lấy trực tiếp các components của một record trong câu lệnh instanceof ra sao?
Bạn mô tả cách record pattern kết hợp type test và component extraction chỉ khi đối tượng phù hợp như thế nào?
Bạn phân biệt record pattern với việc gọi từng accessor thủ công của record sau instanceof type check ra sao?
Bạn sẽ thiết kế record Point có hai components và dùng pattern để trích tọa độ trước khi tính khoảng cách như thế nào?
Bạn mô tả nested record patterns giúp phân rã một record chứa record khác theo cấu trúc nào?
Bạn sẽ viết một record pattern để trích trường của Order chứa Customer và Address records ra sao?
Bạn phân tích vì sao record pattern không phải phép phân rã tùy ý mọi class có getter tương tự record ra sao?
Bạn sẽ kiểm tra trường hợp selector object là null khi dùng instanceof record pattern như thế nào?
Bạn mô tả khi một component là null, record pattern với nested pattern có thể match hoặc không match theo điều kiện nào?
Bạn sẽ so sánh pattern dùng var cho component với pattern có kiểu tường minh theo tính rõ nghĩa như thế nào?
Bạn giải thích compiler suy luận kiểu của var pattern variables từ record component types như thế nào?
Bạn sẽ sử dụng var trong record pattern để tránh khai báo lặp kiểu generic đã biết theo cách nào?
Bạn phân tích vì sao một component trích ra bằng var vẫn cần validation nghiệp vụ trước khi sử dụng ra sao?
Bạn sẽ sử dụng record pattern lồng nhau để giảm số lượng cast nhưng không làm điều kiện trở nên khó đọc như thế nào?
Bạn mô tả thứ tự và số lượng nested component patterns phải phù hợp với record header như thế nào?
Bạn sẽ thiết kế tên biến record pattern tránh che khuất một biến trong scope bên ngoài ra sao?
Bạn phân biệt scope của record pattern variables trong instanceof với biến local bình thường theo flow scoping như thế nào?
Bạn sẽ viết điều kiện instanceof với record pattern kết hợp && để kiểm tra thêm giá trị component ra sao?
Bạn phân tích vì sao không thể dùng biến pattern ở nhánh logic mà compiler chưa chứng minh pattern đã match ra sao?
Bạn sẽ sử dụng guard clause để kiểm tra record pattern rồi return sớm khi type không phù hợp như thế nào?
Bạn mô tả khi nào nên tách nhiều nested patterns thành helper methods để giữ code dễ đọc ra sao?
Bạn sẽ sử dụng record pattern trong một switch expression để trả về kết quả dựa trên components như thế nào?
Bạn phân biệt record pattern trong switch với type pattern trong switch về lượng thông tin được rút ra như thế nào?
Bạn sẽ thiết kế switch xử lý một sealed hierarchy gồm các records với patterns tương ứng ra sao?
Bạn phân tích vì sao pattern matching cần xử lý record components nullable theo các case riêng khi business rules yêu cầu như thế nào?
Bạn sẽ cân nhắc khi nào dùng accessor method trực tiếp thay record pattern vì cần gọi method nhiều lần hoặc có validation riêng ra sao?
Bạn mô tả compiler kiểm tra generic record patterns bằng các thông tin kiểu có thể suy luận tại compile time như thế nào?
Bạn sẽ sử dụng record pattern với generic record Box chứa String mà không kỳ vọng runtime giữ mọi type arguments như thế nào?
Bạn phân tích vì sao type erasure vẫn giới hạn một số kiểm tra generic types dù Java 21 có record patterns ra sao?
Bạn sẽ xác định pattern nào bị từ chối biên dịch do generic type không tương thích với selector như thế nào?
Bạn sẽ đánh giá việc đổi record header ảnh hưởng những source code đang dùng record patterns ra sao?
Bạn mô tả vì sao record pattern phụ thuộc public component structure chứ không tự cung cấp backward-compatible schema evolution như thế nào?
Bạn sẽ viết unit tests cho record pattern với nested null values, subtype components và dữ liệu hợp lệ như thế nào?
Bạn phân tích vì sao record patterns không tự kiểm tra invariants của object nếu constructor cho phép trạng thái sai ra sao?
Bạn sẽ thiết kế refactoring từ instanceof + accessor calls sang record pattern mà không làm thay đổi exception behavior như thế nào?
Bạn mô tả vì sao record patterns phù hợp nhất cho dữ liệu có cấu trúc ổn định thay vì mutable object graph phức tạp như thế nào?
Bạn giải thích pattern matching cho switch được chuẩn hóa ở Java 21 mở rộng các nhãn case như thế nào?
Bạn sẽ chuyển một chuỗi if-instanceof phân loại objects sang switch expression với type patterns ra sao?
Bạn mô tả cách type pattern trong switch vừa kiểm tra kiểu vừa khai báo pattern variable như thế nào?
Bạn phân biệt switch statement và switch expression khi mỗi nhánh cần trả một kết quả theo ngữ nghĩa nào?
Bạn sẽ dùng switch expression với các case pattern để trả một immutable result từ nhiều loại input như thế nào?
Bạn giải thích việc sử dụng từ khóa when để thêm guard condition vào một case pattern trong Java 21 ra sao?
Bạn sẽ kết hợp record pattern và when guard để phân loại giao dịch theo giá trị record components như thế nào?
Bạn mô tả vì sao guard expression phải có kiểu boolean và chỉ được đánh giá khi pattern đã match như thế nào?
Bạn sẽ thiết kế thứ tự các case cho superclass và subtype để tránh lỗi dominance trong pattern switch ra sao?
Bạn phân tích vì sao case Object đặt trước case String làm case phía sau bị chi phối khi selector phù hợp như thế nào?
Bạn sẽ phân biệt dominance giữa unguarded type pattern và guarded pattern theo quy tắc biên dịch nào?
Bạn mô tả vì sao một case với guard không hằng có thể không thống trị mọi trường hợp của type pattern ra sao?
Bạn sẽ xác định nhãn case không thể tới được vì một pattern tổng quát đã match trước đó bằng cách nào?
Bạn sẽ dùng case null để xử lý selector null tường minh thay vì dựa vào default như thế nào?
Bạn phân tích vì sao cần kiểm tra hành vi với selector null khi chuyển từ switch cũ sang pattern switch ra sao?
Bạn sẽ tổ chức case null, case các kiểu cụ thể và default theo mức độ ưu tiên của business rules như thế nào?
Bạn mô tả cơ chế exhaustive checking của switch expression trong Java 21 với một sealed interface ra sao?
Bạn sẽ thiết kế sealed hierarchy gồm thành công, thất bại và chờ xử lý để switch covers tất cả variants như thế nào?
Bạn phân biệt exhaustive switch trên sealed hierarchy với switch phải có default khi compiler không chứng minh đủ nhánh ra sao?
Bạn sẽ kiểm tra khả năng exhaustive của switch trên enum khi danh sách constants được mở rộng giữa các phiên bản như thế nào?
Bạn phân tích vì sao thêm một permitted subclass vào sealed hierarchy có thể buộc cập nhật switch ở các module tiêu thụ ra sao?
Bạn sẽ chọn default branch hay liệt kê đủ các sealed subclasses để compiler hỗ trợ phát hiện thay đổi model như thế nào?
Bạn sẽ phân tích hành vi runtime khi switch được biên dịch với giả định exhaustive nhưng gặp một variant mới ngoài các case đã biết như thế nào?
Bạn sẽ kiểm thử bảo đảm exhaustive switch sau khi nâng phiên bản một dependency chứa sealed hierarchy như thế nào?
Bạn phân biệt switch pattern checking với polymorphic dispatch trong thiết kế mở rộng hệ thống ra sao?
Bạn sẽ sử dụng yield khi một case của switch expression cần một block gồm nhiều câu lệnh ra sao?
Bạn mô tả cách arrow switch labels giúp tránh accidental fall-through so với colon labels trong code cũ như thế nào?
Bạn sẽ quyết định khi nào dùng một case guard thay vì tạo method helper có tên nghiệp vụ như thế nào?
Bạn phân tích vì sao guard có side effects làm pattern switch khó dự đoán khi điều kiện thay đổi ra sao?
Bạn sẽ tránh dựa vào thứ tự side effects của guard để cập nhật state của domain model như thế nào?
Bạn mô tả cách pattern variable trong mỗi case có scope phù hợp với phần xử lý của case đó ra sao?
Bạn sẽ kiểm tra biến pattern không bị truy cập từ nhánh case khác nơi nó chưa được gán ra sao?
Bạn phân biệt type patterns với constant patterns của enum hoặc String trong một switch selector ra sao?
Bạn sẽ thiết kế switch trên interface để xử lý String, Integer và record types theo case rõ nghĩa như thế nào?
Bạn mô tả việc kết hợp case null với default cần chú ý nhánh nào để bảo đảm xử lý đúng ra sao?
Bạn sẽ chọn xử lý case null bằng kết quả mặc định hay ném exception theo API contract nào?
Bạn phân tích vì sao type pattern không thể phân biệt mọi generic parameter types sau type erasure ra sao?
Bạn sẽ xác minh một case pattern với generic type chỉ hợp lệ khi compiler có đủ thông tin kiểu như thế nào?
Bạn mô tả cách guarded pattern giúp phân loại record based on amount hoặc status sau khi components được trích ra ra sao?
Bạn sẽ tổ chức một switch expression phân loại HTTP response records thành các trạng thái trả về ra sao?
Bạn phân tích vì sao pattern matching trong switch không mặc nhiên thay thế null checking trên nested record components như thế nào?
Bạn sẽ so sánh sự rõ ràng của nested record pattern với một guard dài gồm nhiều điều kiện như thế nào?
Bạn mô tả ảnh hưởng của việc đổi generic record component types tới các pattern switch đã biên dịch như thế nào?
Bạn sẽ tránh đưa exhaustive business rules vào default khi sealed model có thể biểu diễn rõ các variants như thế nào?
Bạn phân tích vì sao switch expression trả giá trị immutable có thể dễ kiểm thử hơn switch statement mutate local variable ra sao?
Bạn sẽ viết property-based tests bao phủ từng sealed subtype, guard boundary và selector null như thế nào?
Bạn sẽ phân biệt lỗi compile-time dominance với lỗi runtime business validation khi một case không được xử lý như thế nào?
Bạn mô tả lý do nên ưu tiên match các kiểu chuyên biệt trước kiểu tổng quát trong pattern switch ra sao?
Bạn sẽ so sánh các pattern matching switch features final ở Java 21 với tính năng pattern bổ sung trên JDK sau đó như thế nào?
Bạn phân tích vì sao cần dùng --release 21 để tránh vô tình đưa syntax pattern chưa có ở Java 21 vào library target ra sao?
Bạn sẽ dùng sealed classes cùng record patterns để thiết kế model kết quả rõ trạng thái và dễ mở rộng có kiểm soát như thế nào?
Bạn mô tả khi nào nên dùng Visitor pattern thay vì switch pattern nếu logic phân tán trong nhiều modules ra sao?
Bạn sẽ thiết kế refactoring từ instanceof chain sang pattern switch có regression tests cho exception và null handling như thế nào?
Bạn phân tích vì sao một switch statement vẫn cần cân nhắc hiệu quả đọc hiểu khi lồng quá nhiều record patterns ra sao?
Bạn giải thích Sequenced Collections của Java 21 thống nhất các collection có encounter order như thế nào?
Bạn phân biệt SequencedCollection, SequencedSet và SequencedMap theo loại dữ liệu cùng contract nào?
Bạn sẽ xác định khi nào một List đã có thứ tự phần tử có thể được sử dụng qua SequencedCollection API ra sao?
Bạn mô tả getFirst và getLast làm việc với hai đầu một SequencedCollection như thế nào?
Bạn sẽ dùng addFirst và addLast để thêm phần tử ở đầu hoặc cuối khi implementation hỗ trợ ra sao?
Bạn phân tích vì sao không phải mọi implementation của SequencedCollection đều hỗ trợ mọi operation sửa đổi ra sao?
Bạn sẽ xử lý NoSuchElementException khi gọi getFirst trên SequencedCollection rỗng như thế nào?
Bạn phân biệt removeFirst và removeLast với việc dùng index hoặc iterator để xóa phần tử như thế nào?
Bạn sẽ thiết kế một API nhận SequencedCollection thay vì List khi chỉ cần truy cập hai đầu như thế nào?
Bạn mô tả reversed trả một view theo thứ tự đảo ngược thay vì mặc định sao chép nội dung như thế nào?
Bạn sẽ kiểm tra việc thay đổi qua reversed view có ảnh hưởng collection gốc theo quy tắc implementation nào?
Bạn phân tích vì sao reversed view trên collection unmodifiable không mặc nhiên trở thành collection có thể sửa ra sao?
Bạn sẽ dùng SequencedCollection.reversed để duyệt phần tử từ cuối về đầu mà không đảo trực tiếp nguồn như thế nào?
Bạn mô tả cách hai lần gọi reversed liên hệ với thứ tự phần tử ban đầu theo contract nào?
Bạn sẽ phân biệt reversed view với Collections.reverse biến đổi List tại chỗ như thế nào?
Bạn phân tích vì sao giữ reversed view trong thời gian dài trên mutable backing collection có thể dẫn đến kết quả thay đổi ra sao?
Bạn sẽ chọn snapshot độc lập hay reversed view tùy yêu cầu concurrency và lifecycle như thế nào?
Bạn mô tả addFirst trên ArrayList và trên LinkedList có thể khác nhau về chi phí thao tác như thế nào?
Bạn sẽ dùng List.getFirst trên JDK 21 thay cho list.get(0) theo điều kiện collection không rỗng ra sao?
Bạn phân biệt getLast trên List với lấy phần tử cuối bằng index size trừ một theo readability và behavior nào?
Bạn sẽ kiểm tra compatibility của code gọi List.reversed khi project còn build target Java 17 như thế nào?
Bạn mô tả vì sao HashSet không cung cấp một encounter order xác định như LinkedHashSet ra sao?
Bạn sẽ dùng LinkedHashSet qua SequencedSet để thao tác đầu hoặc cuối khi order có ý nghĩa như thế nào?
Bạn phân biệt SequencedSet với Set thông thường về khả năng đại diện thứ tự duyệt như thế nào?
Bạn mô tả LinkedHashSet.addFirst và addLast có thể điều chỉnh vị trí phần tử đã tồn tại theo contract nào?
Bạn sẽ thiết kế tests cho SequencedSet tránh có hai phần tử equals true dù thao tác addFirst hoặc addLast như thế nào?
Bạn phân tích vì sao unique elements của SequencedSet vẫn phụ thuộc equals và hashCode theo underlying implementation ra sao?
Bạn sẽ kiểm tra thứ tự iteration của LinkedHashSet sau các thao tác addFirst, addLast và reversed như thế nào?
Bạn mô tả cách SequencedSet.reversed tạo góc nhìn ngược lại đối với thứ tự các phần tử như thế nào?
Bạn sẽ xác định vì sao TreeSet cũng có thứ tự nhưng không cho phép tự ý chèn phần tử tại đầu cuối trái với comparator ra sao?
Bạn phân biệt encounter order của LinkedHashSet với sorted order của TreeSet theo ý nghĩa nghiệp vụ nào?
Bạn sẽ xử lý UnsupportedOperationException khi gọi thao tác định vị không được sorted set implementation hỗ trợ như thế nào?
Bạn phân tích vì sao thứ tự của TreeSet có thể thay đổi nếu Comparator phụ thuộc vào mutable state của phần tử ra sao?
Bạn sẽ dùng NavigableSet.first hoặc SequencedSet.getFirst theo yêu cầu API compatibility nào?
Bạn mô tả vì sao reversed view của một sorted set thể hiện comparator order ngược chứ không phải insertion order ra sao?
Bạn sẽ chọn SequencedSet cho một quy trình cần giữ lịch sử thứ tự duy nhất nhưng không cần sắp tăng dần như thế nào?
Bạn phân biệt SequencedMap với Map thông thường về ý nghĩa thứ tự của entries như thế nào?
Bạn sẽ sử dụng LinkedHashMap để có iteration order rõ ràng và truy cập qua SequencedMap API như thế nào?
Bạn mô tả firstEntry và lastEntry trên SequencedMap cung cấp những thông tin gì khi map không rỗng như thế nào?
Bạn sẽ kiểm tra kết quả firstEntry hoặc lastEntry khi SequencedMap rỗng thay vì giả định luôn có entry ra sao?
Bạn phân biệt pollFirstEntry và pollLastEntry với firstEntry và lastEntry về tác động xóa dữ liệu như thế nào?
Bạn sẽ dùng putFirst hoặc putLast trên LinkedHashMap để thay đổi vị trí key theo nhu cầu nào?
Bạn mô tả việc putFirst đối với key đã tồn tại ảnh hưởng vị trí entry nhưng vẫn giữ uniqueness của key ra sao?
Bạn phân tích vì sao gọi putFirst hoặc putLast trên một sorted map có thể không được hỗ trợ do ràng buộc comparator như thế nào?
Bạn sẽ thiết kế API trả SequencedMap khi caller cần phần tử đầu cuối nhưng không nên phụ thuộc concrete LinkedHashMap ra sao?
Bạn mô tả sequencedKeySet, sequencedValues và sequencedEntrySet phản ánh thứ tự của map theo dạng view nào?
Bạn sẽ sử dụng sequencedEntrySet để duyệt entries ngược chiều khi kết hợp reversed như thế nào?
Bạn phân biệt SequencedMap.reversed với tạo TreeMap có reversed comparator theo semantics nào?
Bạn sẽ xác định thứ tự access-order của LinkedHashMap so với insertion-order trong use case LRU cache ra sao?
Bạn phân tích vì sao truy cập entry trong LinkedHashMap cấu hình access-order có thể thay đổi encounter order theo operation nào?
Bạn sẽ đánh giá các thao tác putFirst, putLast tương tác với access-order LinkedHashMap theo contract nào?
Bạn sẽ thiết kế bounded cache dùng LinkedHashMap nhưng không giả định SequencedMap tự đảm bảo thread safety như thế nào?
Bạn mô tả cách SequencedMap firstEntry và lastEntry giúp làm rõ thao tác eviction thủ công như thế nào?
Bạn sẽ sử dụng Collections.unmodifiableSequencedCollection để xuất view không cho caller sửa theo quy tắc nào?
Bạn phân biệt unmodifiableSequencedMap wrapper với copy độc lập của một Map có thứ tự theo ownership nào?
Bạn phân tích vì sao Map.copyOf không cung cấp SequencedMap API và không phải giải pháp giữ encounter order trong mọi trường hợp ra sao?
Bạn sẽ kiểm thử reversed view khi map gốc bị sửa thông qua reference khác theo các kỳ vọng nào?
Bạn mô tả sự khác nhau giữa duyệt SequencedMap qua entrySet và sequencedEntrySet khi cần contract về kiểu view ra sao?
Bạn sẽ viết tests cho empty, singleton và multi-entry SequencedCollections khi gọi getFirst hoặc removeLast như thế nào?
Bạn sẽ kiểm tra một collection tùy chỉnh implements SequencedCollection tuân thủ reversed view contract ra sao?
Bạn phân tích vì sao chọn SequencedCollection làm parameter type có thể cải thiện API nhưng ràng buộc minimal JDK 21 ra sao?
Bạn sẽ thiết kế chuyển đổi dữ liệu từ HashMap sang LinkedHashMap mà không giả định HashMap có thứ tự đầu vào cố định như thế nào?
Bạn mô tả khi nào dùng Sequenced Collections rõ ý hơn thao tác List thủ công nhưng không đem lại lợi thế thuật toán như thế nào?
Bạn sẽ đánh giá hiệu năng của reversed views và thao tác đầu cuối trên nhiều implementations bằng workload nào?
Bạn giải thích virtual threads được chuẩn hóa ở Java 21 giải quyết vấn đề chi phí thread-per-request như thế nào?
Bạn phân biệt virtual threads với platform threads về khả năng scale số tác vụ blocking ra sao?
Bạn sẽ xác định vì sao virtual threads phù hợp với I/O-bound workload hơn là tăng tốc CPU-bound computation như thế nào?
Bạn mô tả mối quan hệ giữa virtual thread và carrier platform thread theo mô hình lập lịch của JVM ra sao?
Bạn sẽ dùng Thread.startVirtualThread để chạy một Runnable độc lập trên virtual thread như thế nào?
Bạn phân biệt Thread.ofVirtual với Thread.ofPlatform khi cấu hình và khởi chạy threads theo công việc ra sao?
Bạn sẽ dùng Thread.ofVirtual().name để đặt tên giúp chẩn đoán hàng nghìn virtual threads như thế nào?
Bạn mô tả Thread.currentThread().isVirtual hỗ trợ quan sát loại thread trong một tác vụ như thế nào?
Bạn sẽ lựa chọn Thread.Builder.OfVirtual và ThreadFactory khi cần tạo virtual threads theo quy ước chung ra sao?
Bạn phân tích vì sao không nên sử dụng một pool tái sử dụng virtual threads chỉ để giới hạn số nhiệm vụ I/O ra sao?
Bạn sẽ dùng Executors.newVirtualThreadPerTaskExecutor để thực thi mỗi nhiệm vụ trên một virtual thread như thế nào?
Bạn phân biệt newVirtualThreadPerTaskExecutor với fixed thread pool theo cách phân phối tasks và giới hạn concurrency ra sao?
Bạn sẽ quản lý vòng đời ExecutorService tạo virtual threads bằng try-with-resources trên Java 21 như thế nào?
Bạn mô tả khi close ExecutorService có thể chờ các nhiệm vụ kết thúc theo lifecycle contract ra sao?
Bạn sẽ thiết kế timeout và cancellation để tránh chờ không giới hạn khi đóng virtual-thread executor như thế nào?
Bạn phân tích vì sao tạo virtual threads rẻ không có nghĩa được phép tạo vô hạn network connections ra sao?
Bạn sẽ dùng Semaphore để giới hạn số requests đồng thời tới dịch vụ ngoài nhưng vẫn cho phép virtual threads chờ ra sao?
Bạn phân biệt giới hạn concurrency tại resource boundary với việc giới hạn số virtual threads được tạo như thế nào?
Bạn sẽ thiết kế một HTTP client request handler thực thi blocking API trên virtual thread theo mô hình nào?
Bạn mô tả cách blocking socket operations có thể nhường carrier thread khi virtual thread chờ I/O như thế nào?
Bạn sẽ kiểm tra sự khác biệt giữa blocking I/O tương thích virtual threads và native blocking call không nhường carrier theo điều kiện nào?
Bạn phân tích vì sao một blocking operation của thư viện ngoài cần được kiểm tra thực tế trước khi mặc định cho rằng nó scale tốt ra sao?
Bạn sẽ so sánh mô hình thread-per-request trên virtual threads với CompletableFuture khi xử lý cùng I/O workflow như thế nào?
Bạn mô tả vì sao virtual threads cho phép mã tuần tự dễ đọc hơn trong nhiều luồng I/O bất đồng bộ ra sao?
Bạn sẽ lựa chọn synchronous client API chạy trong virtual threads hay non-blocking API theo đặc điểm workload nào?
Bạn phân tích vì sao thay platform threads bằng virtual threads không tự loại bỏ deadlock do ứng dụng thiết kế sai ra sao?
Bạn sẽ dùng try/finally bảo đảm resource cleanup khi tác vụ virtual thread bị interrupt như thế nào?
Bạn mô tả Thread.interrupt và InterruptedException vẫn có vai trò gì trong hủy tác vụ virtual threads ra sao?
Bạn sẽ xây một request timeout policy có xử lý interruption mà không nuốt tín hiệu hủy như thế nào?
Bạn phân tích vì sao catch InterruptedException rồi tiếp tục chạy có thể làm shutdown virtual threads bị kẹt ra sao?
Bạn sẽ chọn ExecutorService.submit trả Future khi cần lấy kết quả và hủy task ra sao?
Bạn mô tả Future.get có timeout giúp caller quản lý thời gian chờ một tác vụ như thế nào?
Bạn sẽ thiết kế fan-out một request tới nhiều backend services bằng virtual-thread executor và Future results ra sao?
Bạn phân tích vì sao failure ở một task không mặc nhiên hủy toàn bộ sibling tasks nếu dùng các Future độc lập ra sao?
Bạn sẽ tổ chức cơ chế cancel các tác vụ không còn cần thiết khi một backend failure khiến request không thể hoàn tất như thế nào?
Bạn mô tả tại sao không nên giả định mọi virtual thread sẽ có platform thread riêng cố định suốt vòng đời ra sao?
Bạn sẽ kiểm tra tính công bằng khi rất nhiều virtual threads tranh chấp một semaphore theo cấu hình nào?
Bạn phân tích vì sao virtual threads giảm chi phí thread stack nhưng không giảm footprint của object graph mỗi request ra sao?
Bạn sẽ đánh giá memory usage của millions of blocked tasks bằng metrics và heap analysis thay vì chỉ đếm OS threads ra sao?
Bạn mô tả vì sao một virtual thread vẫn có stack trace và identity riêng hữu ích cho debugging ra sao?
Bạn sẽ dùng ThreadLocal trên virtual threads nhưng cân nhắc lifetime của context và số lượng task như thế nào?
Bạn phân biệt ThreadLocal trên virtual-thread-per-request với ThreadLocal trên pooled platform threads theo rủi ro giữ state ra sao?
Bạn phân tích vì sao cache một connection đắt tiền trong ThreadLocal của từng virtual thread có thể phá pooling policy ra sao?
Bạn sẽ thiết kế connection pooling ở tầng data source thay vì gắn connection cố định vào từng virtual thread như thế nào?
Bạn mô tả khi nào cần xóa sensitive context trong ThreadLocal trước khi task virtual thread hoàn tất ra sao?
Bạn sẽ kiểm tra thư viện dùng InheritableThreadLocal có thể truyền dữ liệu không cần thiết sang rất nhiều virtual threads như thế nào?
Bạn phân tích vì sao ThreadLocal không tự động thay thế context propagation khi dùng async callbacks chạy trên executor khác ra sao?
Bạn sẽ dùng logging correlation ID và ThreadLocal/MDC với try/finally để không làm rò dữ liệu giữa tasks ra sao?
Bạn mô tả vì sao virtual threads không bảo đảm thay đổi thứ tự thực thi của synchronized blocks theo nguyên tắc nào?
Bạn sẽ đánh giá cách thread naming và structured logs giúp điều tra hàng nghìn virtual threads trong một hệ thống ra sao?
Bạn phân tích vì sao không nên dùng Thread.getAllStackTraces để làm giám sát thường xuyên cho lượng virtual threads rất lớn ra sao?
Bạn giải thích hiện tượng virtual-thread pinning trên JDK 21 làm carrier thread không thể được giải phóng trong một số blocking operations như thế nào?
Bạn sẽ phân biệt virtual thread bị parked bình thường với virtual thread bị pinned trên carrier thread theo tác động nào?
Bạn mô tả vì sao blocking operation nằm trong synchronized block ở JDK 21 cần được đánh giá về carrier pinning ra sao?
Bạn sẽ kiểm tra những thay đổi trên JDK mới hơn, đặc biệt việc loại bỏ một số nguyên nhân pinning từ synchronized, trước khi áp dụng lời khuyên cũ như thế nào?
Bạn phân tích vì sao không thể mặc định rằng mọi đoạn synchronized sẽ gây pinning trên mọi JDK hiện đại ra sao?
Bạn sẽ dùng JFR event jdk.VirtualThreadPinned trên JDK 21 để tìm các điểm nghẽn có liên quan như thế nào?
Bạn mô tả khi JFR event của virtual thread thay đổi giữa các JDK thì cần kiểm tra recording settings và release notes ra sao?
Bạn sẽ xem xét giá trị thực tế của -Djdk.tracePinnedThreads trên JDK 21 nhưng không sao chép cờ này mù quáng sang JDK mới như thế nào?
Bạn sẽ phân tích stack trace pinning để xác định đoạn blocking I/O nằm trong monitor critical section ra sao?
Bạn mô tả vì sao code native hoặc foreign calls có thể có đặc điểm scheduling khác với Java blocking APIs thông thường như thế nào?
Bạn sẽ cân nhắc thay một synchronized critical section có blocking I/O bằng cơ chế coordination phù hợp mà vẫn giữ thread safety như thế nào?
Bạn phân tích vì sao không nên chuyển tất cả synchronized blocks sang ReentrantLock chỉ vì ứng dụng dùng virtual threads ra sao?
Bạn sẽ so sánh JDK 21 và JDK mới hơn bằng cùng workload để đo carrier utilization và latency khi có lock contention như thế nào?
Bạn mô tả cách blocking database driver ảnh hưởng throughput của virtual threads khi connection pool nhỏ như thế nào?
Bạn sẽ dùng metrics của connection pool để xác định vì sao thêm virtual threads không làm số database operations tăng ra sao?
Bạn phân tích vì sao virtual threads không tạo thêm database capacity và cần bảo vệ connection limits như thế nào?
Bạn sẽ thiết kế load test nhiều requests chờ I/O để so sánh platform-thread pool với virtual-thread-per-task executor ra sao?
Bạn mô tả vì sao nên đo p95, p99 latency và end-to-end throughput thay vì chỉ đếm threads ra sao?
Bạn sẽ đánh giá memory pressure từ quá nhiều queued tasks và request payloads dù mỗi virtual thread nhẹ như thế nào?
Bạn phân tích vì sao dùng virtual threads cho CPU-intensive loops không tự tăng sức mạnh xử lý của CPU ra sao?
Bạn sẽ lập kế hoạch bounded concurrency bằng Semaphore hoặc rate limiter cho virtual-thread workload theo SLA nào?
Bạn mô tả vì sao thread pools cho CPU-bound workloads vẫn có thể phù hợp hơn thread-per-task vô giới hạn như thế nào?
Bạn sẽ phân biệt Thread.sleep trên virtual thread với blocking native sleep theo khả năng nhường carrier như thế nào?
Bạn phân tích vì sao code bận chờ bằng vòng while trên virtual thread gây lãng phí CPU tương tự platform thread ra sao?
Bạn sẽ xử lý interruption đúng trong một virtual-thread task dùng sleep hoặc blocking socket operation như thế nào?
Bạn mô tả cách shutdownNow tác động đến các tasks đang chạy và vai trò của cooperative cancellation ra sao?
Bạn sẽ kiểm tra resource cleanup khi một virtual-thread task giữ lock hoặc connection lúc nhận cancellation như thế nào?
Bạn phân tích vì sao thread dump truyền thống có thể không trình bày đầy đủ mọi virtual thread và cần chọn diagnostic tool thích hợp ra sao?
Bạn sẽ sử dụng jcmd Thread.dump_to_file ở JDK hỗ trợ để thu virtual-thread-aware thread dumps theo cách nào?
Bạn mô tả khi nào chọn JSON thread dump so với text output để phân tích số lượng lớn virtual-thread stacks ra sao?
Bạn sẽ dùng JFR theo dõi virtual-thread lifecycle events mà vẫn kiểm soát event volume trong production như thế nào?
Bạn phân tích vì sao bật recording tất cả thread start/end events trên workload lớn có thể gây overhead hoặc log volume tăng ra sao?
Bạn sẽ gắn request ID vào application logs và correlate với JFR để tìm các virtual-thread tasks bị chậm như thế nào?
Bạn mô tả vì sao OS thread count không tương đương số virtual threads đang sống trong JVM như thế nào?
Bạn sẽ thiết kế dashboards theo task queueing, pool saturation, carrier pressure và downstream capacity như thế nào?
Bạn phân tích vì sao chỉ xem số OS threads thấp không chứng minh virtual-thread migration thành công như thế nào?
Bạn sẽ kiểm thử thread-local context isolation giữa nhiều virtual-thread tasks chạy đồng thời như thế nào?
Bạn mô tả yêu cầu phải tránh thread affinity assumptions trong các third-party libraries sử dụng virtual threads ra sao?
Bạn sẽ rà soát JDBC, HTTP, filesystem và logging dependencies trước khi đổi executor sang virtual threads theo trình tự nào?
Bạn phân tích vì sao dùng virtual threads không tự khắc phục race conditions do shared mutable state ra sao?
Bạn sẽ triển khai canary release cho virtual-thread migration và so sánh error rates cùng latency như thế nào?
Bạn mô tả cách rollback thread model nếu phát hiện deadlocks, resource exhaustion hoặc throughput regression ra sao?
Bạn sẽ viết regression tests chạy trên JDK 21 và JDK mới để phát hiện sự thay đổi pinning behavior theo cách nào?
Bạn giải thích Generational ZGC được giới thiệu trong Java 21 mở rộng ZGC bằng cách phân chia generations như thế nào?
Bạn mô tả vì sao phần lớn objects thường chết khi còn trẻ và nhận định này có ích cho generational collection ra sao?
Bạn phân biệt young generation với old generation trong Generational ZGC theo vòng đời object nào?
Bạn sẽ giải thích cơ chế chuyển những object còn sống qua các generations khi dùng Generational ZGC như thế nào?
Bạn phân tích vì sao Generational ZGC hướng tới duy trì pause time thấp nhưng vẫn phải cân nhắc CPU và memory overhead ra sao?
Bạn sẽ phân biệt yêu cầu low latency với mục tiêu maximum throughput khi so sánh ZGC và các collectors khác như thế nào?
Bạn mô tả việc phân tách young/old generations ảnh hưởng tần suất thu gom các objects mới tạo ra sao?
Bạn sẽ xem GC logs để nhận diện hoạt động thu gom young và old trong generational ZGC như thế nào?
Bạn phân tích vì sao tổng thời gian GC CPU và stop-the-world pause là các chỉ số khác nhau như thế nào?
Bạn sẽ thiết lập một baseline về allocation rate, live set, heap occupancy và p99 latency trước khi đổi GC ra sao?
Bạn mô tả cách xác định collector thực tế bằng JVM flags hoặc GC startup logs theo từng phiên bản JDK như thế nào?
Bạn sẽ bật Generational ZGC trên đúng JDK 21 với các JVM options phù hợp rồi kiểm tra lại qua logs như thế nào?
Bạn phân tích vì sao không nên áp dụng nguyên xi cờ -XX:+ZGenerational của JDK 21 cho mọi JDK mới hơn như thế nào?
Bạn sẽ kiểm tra default mode của ZGC trên JDK mới trước khi kết luận phải bật generational bằng một option riêng ra sao?
Bạn mô tả vì sao khả năng hỗ trợ non-generational ZGC có thể khác theo các release Java và cần đọc option reference ra sao?
Bạn sẽ chọn heap size hợp lý cho Generational ZGC khi ứng dụng chịu spike allocation lớn như thế nào?
Bạn phân tích vì sao một heap quá nhỏ có thể làm GC hoạt động liên tục dù pause mỗi lần vẫn ngắn ra sao?
Bạn sẽ phân biệt memory consumption được báo bằng heap committed với process RSS khi dùng ZGC ra sao?
Bạn mô tả vì sao native memory, thread stacks và code cache vẫn cần tính vào memory limit của container ra sao?
Bạn sẽ so sánh G1 và Generational ZGC bằng cùng workload nhưng không giả định một collector luôn thắng như thế nào?
Bạn phân tích vì sao benchmark chỉ chạy vài giây có thể bỏ qua warming, class loading và long-lived objects ra sao?
Bạn sẽ dùng JFR recording và GC logs để tìm tương quan giữa allocation bursts với latency spikes như thế nào?
Bạn sẽ phân tích hiện tượng allocation stalls khi tốc độ cấp phát vượt khả năng thu gom của GC như thế nào?
Bạn sẽ chẩn đoán hệ thống gặp allocation stalls dù ZGC có mục tiêu low pause times như thế nào?
Bạn phân tích vì sao memory leak ở application layer không thể được xử lý triệt để chỉ bằng đổi GC ra sao?
Bạn sẽ kiểm tra long-lived cache và reference retention nếu old generation occupancy tăng lâu dài như thế nào?
Bạn mô tả vai trò của object allocation profile khi tối ưu code tạo quá nhiều short-lived objects ra sao?
Bạn sẽ cân nhắc ảnh hưởng của barrier overhead tới CPU khi lựa chọn generational collector ra sao?
Bạn phân tích vì sao một GC collector có pause tốt có thể vẫn làm application throughput giảm trong một số workload ra sao?
Bạn sẽ thiết kế so sánh p50, p95 và p99 request latency giữa các collector theo cùng traffic patterns như thế nào?
Bạn mô tả vì sao CPU utilization, throughput và heap occupancy phải được đo đồng thời với GC pause ra sao?
Bạn sẽ kiểm tra GC logs có bị thiếu hoặc rotate sớm trước khi phân tích một production incident như thế nào?
Bạn phân tích vì sao dùng log file quá lớn cho GC diagnostics có thể tạo thêm chi phí I/O ra sao?
Bạn sẽ dùng jcmd để xác định JVM flags và GC heap information ở runtime trước khi sửa cấu hình ra sao?
Bạn mô tả khi nào chọn tăng heap thay vì chuyển collector sau khi đánh giá allocation pressure theo số liệu nào?
Bạn sẽ xác định ngưỡng memory request và limit trong Kubernetes phù hợp với heap cùng non-heap memory ra sao?
Bạn phân tích vì sao memory tuning trên Java 21 cần tái kiểm tra khi chuyển sang JDK mới có ZGC implementation thay đổi ra sao?
Bạn sẽ xây performance test có warm-up, steady state, peak traffic và recovery để so sánh Generational ZGC như thế nào?
Bạn mô tả cách kiểm tra GC performance với workload vừa tạo records ngắn sống vừa giữ caches lâu dài ra sao?
Bạn sẽ phân biệt pause time regression từ JVM với latency regression do database hoặc network bằng dữ liệu nào?
Bạn phân tích vì sao chỉ xem GC time percentage chưa đủ để chứng minh cải tiến người dùng nhận được ra sao?
Bạn sẽ thiết lập canary rollout cho thay đổi GC và xác định metrics đủ để quyết định rollback như thế nào?
Bạn mô tả cách bảo vệ dữ liệu nhạy cảm trong JFR events, heap dumps và GC-related incident reports ra sao?
Bạn sẽ kiểm tra tài liệu các bản JDK để phân biệt một ZGC tuning flag đã thay đổi hoặc không còn hỗ trợ như thế nào?
Bạn phân tích vì sao nên giữ cấu hình JVM tối thiểu và ưu tiên defaults đã được kiểm chứng thay vì sao chép nhiều flags cũ ra sao?
Bạn sẽ đánh giá sự khác nhau của Generational ZGC giữa Java 21 và JDK mới mà vẫn giữ nguyên business workload như thế nào?
Bạn sẽ kiểm tra Key Encapsulation Mechanism API được chuẩn hóa ở Java 21 còn phù hợp trong JCA workflows trên JDK mới như thế nào?
Bạn phân biệt Key Encapsulation Mechanism với chữ ký số và mã hóa dữ liệu trực tiếp theo vai trò mật mã nào?
Bạn sẽ kiểm tra provider hỗ trợ một KEM algorithm cụ thể trước khi tích hợp API chuẩn của Java như thế nào?
Bạn phân tích vì sao API KEM không thay thế quy trình xác thực danh tính và quản lý khóa an toàn ra sao?
Bạn sẽ thiết kế crypto interoperability tests khi dùng Java 21 KEM API và provider được hỗ trợ hiện tại như thế nào?
Bạn mô tả các cảnh báo dynamic agent loading được Java 21 đưa ra giúp chuẩn bị cho thay đổi chính sách JVM sau này ra sao?
Bạn sẽ kiểm tra công cụ profiling hoặc testing phụ thuộc dynamic attach để đánh giá tương thích với JDK mới như thế nào?
Bạn phân tích vì sao nên ưu tiên cấu hình Java agents rõ ràng tại startup khi toolchain yêu cầu theo chính sách deployment ra sao?
Bạn sẽ rà soát JDK 21 release notes để phân biệt agent-loading warning với lỗi ứng dụng thực tế theo điều kiện nào?
Bạn sẽ viết compile test với --release 21 để bảo đảm code không vô tình phụ thuộc API chỉ xuất hiện trên JDK sau như thế nào?
Bạn mô tả vì sao các API từng preview trong Java 21 không nên được đưa vào thư viện mới dưới dạng hợp đồng ổn định của release này ra sao?
Bạn sẽ xây migration checklist kiểm tra record patterns, sealed switches, Sequenced Collections và virtual thread behavior trên JDK hiện đại như thế nào?
Bạn phân tích vì sao API Java 21 có thể ổn định về cú pháp nhưng implementation của GC hoặc scheduler vẫn đổi theo JDK ra sao?
Bạn sẽ xác định khi nào một dependency dùng bytecode transformation cần nâng cấp để nhận diện Java 21 class files như thế nào?
Bạn mô tả cách so sánh startup, throughput, p99 latency và RSS giữa Java 17 và Java 21 với cùng workload ra sao?
Nếu nested record pattern không match do một component null, bạn sẽ sửa pattern hoặc điều kiện kiểm tra theo domain semantics như thế nào?
Nếu một record component đổi kiểu làm pattern switch không compile, bạn sẽ đánh giá API compatibility và migration ra sao?
Nếu type pattern đứng trước subtype pattern trong switch gây dominance error, bạn sẽ sắp xếp hoặc thay đổi cases như thế nào?
Nếu switch trên sealed hierarchy thiếu một permitted subtype, bạn sẽ dùng compiler diagnostics để bổ sung xử lý như thế nào?
Nếu selector null đi vào pattern switch và ném exception ngoài mong muốn, bạn sẽ khai báo case null theo chính sách nào?
Nếu guard when chứa side effects gây kết quả khó dự đoán, bạn sẽ tách business predicate thành hàm thuần túy như thế nào?
Nếu refactoring sang record patterns làm đọc code khó hơn do lồng quá sâu, bạn sẽ đơn giản hóa hoặc dùng accessors khi nào?
Nếu LinkedHashSet được sửa bằng addFirst nhưng kết quả tests không như mong đợi, bạn sẽ kiểm tra uniqueness và encounter order như thế nào?
Nếu TreeSet không hỗ trợ addFirst dù là SequencedSet, bạn sẽ giải thích ràng buộc sorted order và sửa client API như thế nào?
Nếu một reversed view thay đổi khi collection gốc bị mutate, bạn sẽ chọn snapshot hoặc view theo hợp đồng nào?
Nếu SequencedMap.firstEntry trả null do map rỗng, bạn sẽ viết nhánh xử lý an toàn như thế nào?
Nếu một LRU cache dùng LinkedHashMap access-order bị thay đổi thứ tự khi đọc, bạn sẽ kiểm tra sequencing assumptions ra sao?
Nếu Map.copyOf làm mất yêu cầu ordering, bạn sẽ chọn cấu trúc SequencedMap có contract rõ ràng như thế nào?
Nếu dùng virtual threads làm connection pool cạn mà throughput không tăng, bạn sẽ giới hạn concurrency và đo downstream saturation ra sao?
Nếu virtual threads dùng ThreadLocal để giữ connection cho từng request và memory tăng, bạn sẽ thay đổi ownership model như thế nào?
Nếu virtual thread bị interrupt nhưng request vẫn chạy, bạn sẽ kiểm tra interruption handling và blocking library behavior ra sao?
Nếu ứng dụng JDK 21 có nhiều virtual-thread pinned events, bạn sẽ tìm blocking critical sections và đối chiếu với JDK mới như thế nào?
Nếu đổi sang JDK mới làm cảnh báo pinning biến mất, bạn sẽ dùng benchmarks để xác minh hiệu quả thực tế thay vì suy luận như thế nào?
Nếu JFR recording không cho thấy virtual-thread events mong đợi, bạn sẽ kiểm tra event availability và recording settings ra sao?
Nếu jstack không hiển thị đầy đủ virtual threads, bạn sẽ dùng thread dump tooling phù hợp với JDK đang chạy như thế nào?
Nếu virtual-thread migration làm CPU tăng trên workload xử lý thuần tính toán, bạn sẽ đánh giá lại thread model ra sao?
Nếu nhiều tasks blocking giữ lượng dữ liệu request lớn khiến heap tăng, bạn sẽ giới hạn in-flight operations như thế nào?
Nếu sau khi bật Generational ZGC trên Java 21 GC logs không cho thấy young/old behavior, bạn sẽ kiểm tra active options như thế nào?
Nếu một JVM option dùng để bật Generational ZGC ở Java 21 không còn hợp lệ trên JDK mới, bạn sẽ cập nhật cấu hình ra sao?
Nếu pause time giảm nhưng throughput và p99 latency vẫn xấu, bạn sẽ điều tra CPU overhead và bottleneck ngoài GC như thế nào?
Nếu container bị OOM kill dù Java heap còn dư, bạn sẽ đo non-heap memory và RSS theo cách nào?
Nếu old generation occupancy tăng liên tục, bạn sẽ phân biệt data retention có chủ ý với memory leak như thế nào?
Nếu nâng Java 21 làm tests với record serialization và module reflection thất bại, bạn sẽ phân loại lỗi compiler, framework và runtime ra sao?
Nếu phải chọn giữa nâng JDK để nhận virtual threads hay refactor toàn bộ I/O sang callbacks, bạn sẽ đánh giá maintenance và load test thế nào?
Nếu muốn triển khai Java 21 cho một dịch vụ nhạy cảm độ trễ, bạn sẽ lập chiến lược canary, metrics, rollback và compatibility tests như thế nào?
