Bạn giải thích vì sao mọi Java class đều có các phương thức cơ bản kế thừa từ Object như thế nào?
Bạn phân biệt object identity với value equality khi hai đối tượng chứa dữ liệu giống nhau ra sao?
Bạn sẽ so sánh toán tử == với Object.equals khi hai biến tham chiếu trỏ tới cùng một object như thế nào?
Bạn mô tả implementation mặc định của Object.equals và ý nghĩa của reference equality như thế nào?
Bạn sẽ xác định khi nào giữ nguyên Object.equals thay vì override theo yêu cầu domain nào?
Bạn phân biệt giá trị của một value object với danh tính của một entity có vòng đời độc lập ra sao?
Bạn sẽ thiết kế lớp biểu diễn tọa độ bất biến theo value semantics thay vì theo object identity như thế nào?
Bạn phân tích vì sao hai instance tạo từ cùng constructor có thể bằng nhau về dữ liệu nhưng khác nhau về identity ra sao?
Bạn sẽ xác định những phương thức nào của Object thường phải được xem xét đồng thời khi thiết kế value class như thế nào?
Bạn mô tả mối quan hệ giữa equals, hashCode và các collection API của Java như thế nào?
Bạn sẽ giải thích vì sao hashCode bằng nhau không chứng minh được hai objects bằng nhau theo equals ra sao?
Bạn phân biệt thứ tự sắp xếp qua compareTo với sự bằng nhau qua equals theo mục đích nào?
Bạn sẽ quyết định khi nào dùng Comparable và khi nào nhận Comparator từ caller theo ngữ nghĩa sắp xếp ra sao?
Bạn phân tích vì sao một class có phương thức toString hữu ích nhưng vẫn không có value equality theo mặc định như thế nào?
Bạn sẽ xác định những bất biến (invariant) nào của class phải được phản ánh trong hợp đồng equals và hashCode ra sao?
Bạn mô tả cách một object mutable có thể thay đổi dữ liệu mà reference identity không thay đổi như thế nào?
Bạn sẽ phân biệt null reference với một object hợp lệ khi đánh giá equals và hashCode ra sao?
Bạn phân tích vì sao không nên gọi equals trên reference có thể null mà không xử lý trước như thế nào?
Bạn sẽ thiết kế API so sánh hai giá trị nullable bằng Objects.equals theo điều kiện nào?
Bạn mô tả tác động của type hierarchy tới value equality khi subclass thêm field quan trọng ra sao?
Bạn sẽ xác định trách nhiệm của một class khi override Object methods nhưng vẫn phải tôn trọng các hợp đồng của JDK như thế nào?
Bạn phân biệt logical equality trong business rules với việc dùng object làm key trong HashMap theo ràng buộc nào?
Bạn sẽ lựa chọn dùng record, immutable class hay class thường khi mô hình hóa dữ liệu theo giá trị như thế nào?
Bạn phân tích vì sao định nghĩa bằng nhau nhất quán là một phần của public API dù không có method public mới ra sao?
Bạn trình bày điều kiện reflexive của equals và những lỗi có thể khiến x.equals(x) trả false như thế nào?
Bạn giải thích hợp đồng symmetric của equals và cách hai lớp trong hierarchy có thể vi phạm nó ra sao?
Bạn sẽ xây ví dụ về transitive equality bị phá vỡ khi thêm thuộc tính ở subclass như thế nào?
Bạn mô tả điều kiện consistent của equals khi trạng thái dùng so sánh không thay đổi ra sao?
Bạn sẽ giải thích vì sao x.equals(null) phải trả false đối với mọi non-null reference như thế nào?
Bạn phân biệt method equality có thể trả false với việc ném ClassCastException khi nhận Object khác kiểu ra sao?
Bạn sẽ chọn những fields nào tham gia equals cho một địa chỉ gồm street, city và postal code theo contract nào?
Bạn phân tích nguy cơ dùng field không ổn định như lastAccessTime trong equals của một cache entry ra sao?
Bạn sẽ phân biệt so sánh primitive fields bằng == và reference fields bằng equals theo kiểu dữ liệu như thế nào?
Bạn mô tả Objects.equals giúp so sánh hai reference nullable mà không gặp NullPointerException ra sao?
Bạn sẽ dùng Arrays.equals để so sánh nội dung một field kiểu mảng primitive trong equals như thế nào?
Bạn phân biệt Arrays.equals với Arrays.deepEquals khi đối tượng chứa mảng lồng nhau theo semantics nào?
Bạn sẽ xử lý field kiểu List trong equals khi thứ tự phần tử có và không có ý nghĩa nghiệp vụ như thế nào?
Bạn mô tả equals của Set phụ thuộc membership thay vì thứ tự iteration như thế nào?
Bạn sẽ đánh giá trường hợp BigDecimal.equals phân biệt scale dù số học biểu diễn cùng giá trị theo nhu cầu nào?
Bạn phân biệt bằng nhau về giá trị của BigDecimal qua compareTo với bằng nhau về representation qua equals ra sao?
Bạn sẽ thiết kế equality cho tiền tệ có amount và currency mà không nhầm hai đơn vị tiền khác nhau như thế nào?
Bạn phân tích vì sao equals không nên gọi network hoặc database để lấy state bổ sung trong lúc so sánh như thế nào?
Bạn sẽ quyết định cách so sánh một trường double khi có NaN, +0.0 và -0.0 theo contract nào?
Bạn mô tả Double.compare hoặc Double.equals hỗ trợ quy tắc equality riêng của floating-point wrapper như thế nào?
Bạn sẽ kiểm tra điều gì khi field dữ liệu có null, empty string hoặc whitespace mà nghiệp vụ coi là khác nhau ra sao?
Bạn phân tích vì sao chuẩn hóa dữ liệu trước khi tạo object dễ giữ equals ổn định hơn chuẩn hóa tạm thời mỗi lần so sánh ra sao?
Bạn sẽ tránh phụ thuộc locale hiện tại khi equals so sánh chuỗi chuẩn hóa hoặc không phân biệt chữ hoa như thế nào?
Bạn mô tả String.equalsIgnoreCase khác quy tắc so sánh tên người theo locale hoặc Unicode normalization như thế nào?
Bạn sẽ thiết kế quy tắc equality rõ nghĩa cho identifier không phân biệt chữ hoa mà vẫn thống nhất với hashCode ra sao?
Bạn phân tích rủi ro dùng hashCode để quyết định equals thay vì so sánh các trường có ý nghĩa như thế nào?
Bạn sẽ kiểm tra tính đối xứng khi equals dùng instanceof còn một subclass override equals với getClass như thế nào?
Bạn mô tả vì sao equals nên tránh side effects lên cả this và other để duy trì consistency như thế nào?
Bạn sẽ định nghĩa một bộ unit tests kiểm tra reflexive, symmetric, transitive, consistent và null behavior của equals như thế nào?
Bạn phân tích vì sao chỉ thử hai object có mọi field giống nhau không chứng minh equals hoạt động đúng ra sao?
Bạn phân biệt sử dụng instanceof và getClass trong equals khi một class có subclass theo hệ quả nào?
Bạn sẽ đánh giá cách dùng getClass để chỉ so sánh cùng runtime class và hạn chế đối với proxy subclasses như thế nào?
Bạn phân tích vì sao equals dùng instanceof ở superclass nhưng subclass thêm field có thể phá symmetry như thế nào?
Bạn sẽ mô hình hóa ví dụ Point và ColoredPoint để chứng minh vấn đề equals trong inheritance ra sao?
Bạn mô tả nguyên tắc dùng composition thay inheritance để giữ value equality ổn định trong trường hợp nào?
Bạn sẽ chọn final class khi muốn không có subclass nào thay đổi hợp đồng equality theo mục tiêu nào?
Bạn phân tích ảnh hưởng của sealed class hierarchy đến việc kiểm soát những subclasses có thể tham gia equality như thế nào?
Bạn sẽ xác định khi nào field của superclass phải được so sánh trong equals của subclass theo hợp đồng nào?
Bạn mô tả cách Objects.equals trên nested value objects giúp xây equality theo cấu trúc như thế nào?
Bạn sẽ phân biệt entity equality trước khi có database ID với sau khi được cấp persistent ID theo chiến lược nào?
Bạn phân tích rủi ro dùng database-generated ID trong hashCode khi entity đã nằm trong HashSet trước khi persist như thế nào?
Bạn sẽ thiết kế equality cho entity có business key bất biến so với surrogate key theo yêu cầu nào?
Bạn mô tả vì sao hai transient entities cùng ID null không nhất thiết phải bằng nhau về business identity ra sao?
Bạn sẽ kiểm tra trường hợp ORM proxy làm runtime class khác entity thật trước khi quyết định getClass hay instanceof như thế nào?
Bạn phân tích vì sao phụ thuộc lazy-loaded fields trong equals có thể kích hoạt truy vấn bất ngờ hoặc lỗi ngoài session như thế nào?
Bạn sẽ tách equality của DTO khỏi equality của entity khi cả hai cùng biểu diễn một đối tượng nghiệp vụ như thế nào?
Bạn phân biệt record value equality với entity identity khi object được cập nhật nhiều lần trong lifecycle ra sao?
Bạn sẽ xác định lúc nào nên dùng một Value Object riêng làm key thay vì dùng mutable domain entity ra sao?
Bạn mô tả rủi ro chọn mọi field bao gồm cached computed values trong equals của một domain object như thế nào?
Bạn sẽ thiết kế giá trị phiên bản (version) của một entity có hay không tham gia equals dựa trên hợp đồng nào?
Bạn phân tích vì sao equals của một JPA entity phải được review cùng với proxy behavior và lifecycle transitions ra sao?
Bạn sẽ xem xét compatibility khi thay đổi các fields được dùng trong equals giữa hai phiên bản thư viện như thế nào?
Bạn mô tả hậu quả khi dữ liệu persisted dưới một quy tắc equality cũ rồi cache chạy với quy tắc mới như thế nào?
Bạn sẽ kiểm thử phép so sánh giữa parent, child và các child siblings để kiểm tra equality trong hierarchy ra sao?
Bạn giải thích hợp đồng Object.hashCode khi hai objects bằng nhau theo equals như thế nào?
Bạn phân biệt điều kiện equals bằng nhau bắt buộc hashCode giống nhau với chiều ngược lại ra sao?
Bạn sẽ mô tả lý do hashCode collision là khả năng bình thường của hashing chứ không mặc nhiên là lỗi như thế nào?
Bạn phân tích vì sao chỉ dùng một giá trị hashCode cố định cho mọi object có thể đúng contract nhưng hiệu năng kém ra sao?
Bạn sẽ chọn các fields tham gia hashCode để nhất quán với fields tham gia equals như thế nào?
Bạn mô tả cách Objects.hash xử lý nhiều giá trị và trade-off về allocation hoặc performance như thế nào?
Bạn sẽ dùng Objects.hashCode cho nullable field mà vẫn giữ contract như thế nào?
Bạn phân biệt Arrays.hashCode với Arrays.deepHashCode đối với mảng phẳng và mảng lồng nhau ra sao?
Bạn sẽ thiết kế hashCode cho object có primitive int, long và boolean theo quy tắc nào?
Bạn mô tả cách String.hashCode deterministic theo chuỗi nội dung khác identity-based hash như thế nào?
Bạn sẽ xác định vì sao không nên suy luận object identity chỉ từ kết quả hashCode ra sao?
Bạn phân tích rủi ro đưa field mutable vào hashCode rồi sửa nó sau khi insert vào HashMap như thế nào?
Bạn sẽ cân nhắc cache hashCode trong immutable class khi tính toán hash phức tạp và được gọi lặp lại ra sao?
Bạn mô tả vì sao cache hashCode trong mutable class có thể tạo kết quả không nhất quán với equals như thế nào?
Bạn sẽ xử lý vấn đề hashCode mặc định của Object đối với object mutable nhưng chưa override equals như thế nào?
Bạn phân biệt System.identityHashCode với obj.hashCode khi class đã override hashCode ra sao?
Bạn sẽ xác định tình huống nào identityHashCode hữu ích trong logging/debug mà không coi nó là unique identifier như thế nào?
Bạn phân tích vì sao hai objects khác identity có thể cùng identityHashCode như thế nào?
Bạn sẽ đánh giá hiệu năng hash distribution qua số collisions và bucket lengths thay vì chỉ kiểm tra tính duy nhất ra sao?
Bạn mô tả cách thay đổi thứ tự kết hợp fields trong hashCode có thể thay distribution dù vẫn đúng contract như thế nào?
Bạn sẽ quyết định khi nào một field optional null tham gia hashCode theo quy tắc equals nào?
Bạn phân tích tại sao không được kỳ vọng hashCode của một object luôn ổn định giữa các JVM executions như thế nào?
Bạn sẽ thiết kế test xác nhận equals và hashCode đồng thời trên objects có nhiều tổ hợp fields ra sao?
Bạn mô tả tại sao hashCode không phù hợp cho xác thực dữ liệu hoặc làm checksum chống sửa đổi như thế nào?
Bạn sẽ phân biệt hashCode 32-bit trong Java collections với cryptographic hashes như SHA-256 theo mục đích nào?
Bạn phân tích vì sao đưa secret trực tiếp vào hashCode/toString có thể tạo nguy cơ bảo mật dù không in plain text ra sao?
Bạn sẽ rà soát ảnh hưởng binary compatibility khi thay đổi implementation hashCode của một public value class như thế nào?
Bạn giải thích HashMap dùng hashCode và equals phối hợp khi put hoặc get key như thế nào?
Bạn sẽ mô tả HashMap xử lý nhiều keys có cùng hashCode qua các bucket như thế nào?
Bạn phân biệt việc trùng hashCode với trùng key theo equals khi thao tác put như thế nào?
Bạn sẽ xác định vì sao HashMap có thể thay giá trị của key cũ nếu equals coi key mới là bằng nhau ra sao?
Bạn mô tả HashSet thường tận dụng hash-based storage để kiểm soát phần tử trùng như thế nào?
Bạn sẽ kiểm tra hành vi HashSet.add khi một object có equality tương đương phần tử đã tồn tại như thế nào?
Bạn phân tích vì sao hashCode không nhất quán làm contains trả false dù value bằng nhau theo equals ra sao?
Bạn sẽ chẩn đoán Map.get trả null sau khi sửa field dùng trong hashCode của key đã được lưu như thế nào?
Bạn phân biệt map trả null do key không tồn tại với map có mapping tới null theo containsKey ra sao?
Bạn sẽ dùng immutable record làm HashMap key trong trường hợp components cũng bất biến theo điều kiện nào?
Bạn mô tả tại sao record chứa mutable array hoặc list có thể vẫn là key nguy hiểm như thế nào?
Bạn sẽ thiết kế key object từ canonical immutable attributes thay vì domain entity mutable như thế nào?
Bạn phân tích vì sao giữ key reference cũ sau khi mutation không bảo đảm HashMap tìm lại key bằng nó ra sao?
Bạn sẽ cân nhắc remove rồi reinsert khi buộc phải thay đổi field của key theo hạn chế nào?
Bạn mô tả thứ tự iteration của HashMap và HashSet không được xem là hợp đồng ổn định như thế nào?
Bạn sẽ phân biệt LinkedHashMap với HashMap khi cần insertion/access order mà vẫn sử dụng equality của keys ra sao?
Bạn sẽ dùng IdentityHashMap khi key identity quan trọng hơn logical equality theo tình huống nào?
Bạn mô tả vì sao IdentityHashMap dùng == và System.identityHashCode khác HashMap như thế nào?
Bạn sẽ đánh giá WeakHashMap dùng key equality đồng thời quản lý reachability của keys theo điều kiện nào?
Bạn phân tích vì sao WeakHashMap không phải bộ nhớ cache có eviction policy đầy đủ như thế nào?
Bạn sẽ kiểm tra HashMap với key có equals đúng nhưng hashCode cố định để quan sát hiệu năng như thế nào?
Bạn sẽ xác định tác động của nhiều collisions lên performance mà không giả định một số thứ tự bucket cụ thể ra sao?
Bạn mô tả tại sao mutable key kết hợp với concurrent modifications có thể gây lỗi logic dù map container thread-safe ra sao?
Bạn sẽ thiết kế test cho equals/hashCode trước khi sử dụng object làm HashSet member theo những trường hợp nào?
Bạn phân tích sự khác nhau giữa map lookup bằng cùng reference và bằng một instance mới có giá trị tương đương ra sao?
Bạn sẽ kiểm tra dữ liệu bị trùng trong HashSet khi một lỗi equals không symmetric xuất hiện giữa các subclasses như thế nào?
Bạn phân biệt contract của hashing trong HashMap với consistency của sorting trong TreeMap như thế nào?
Bạn giải thích Object.toString mặc định cung cấp thông tin gì và vì sao chưa chắc hữu ích cho domain debugging như thế nào?
Bạn sẽ thiết kế toString cho value object sao cho thể hiện state quan trọng nhưng không rò thông tin nhạy cảm như thế nào?
Bạn phân biệt output của toString phục vụ developer với format serialize chính thức của API như thế nào?
Bạn sẽ cân nhắc tên class, identifier và fields nào cần xuất trong toString của một entity như thế nào?
Bạn phân tích nguy cơ in password, access token hoặc thông tin cá nhân qua tự động generate toString như thế nào?
Bạn sẽ dùng Objects.toString với default fallback khi reference có thể null theo mục đích nào?
Bạn mô tả vì sao string concatenation và String.valueOf có thể ngầm gọi toString của object như thế nào?
Bạn sẽ xác định nguyên nhân một logger in object lớn gây tốn CPU do toString đệ quy như thế nào?
Bạn phân tích rủi ro toString của object graph có circular references làm StackOverflowError ra sao?
Bạn sẽ thiết kế toString của graph node không đi sâu vào toàn bộ object graph như thế nào?
Bạn mô tả vì sao một toString không nên gọi database hoặc network chỉ để tạo debug string ra sao?
Bạn sẽ kiểm tra lazy-loaded ORM fields có bị kích hoạt ngoài ý muốn khi toString được gọi như thế nào?
Bạn phân biệt tính ổn định của toString với yêu cầu equals/hashCode theo mức độ contract nào?
Bạn sẽ cân nhắc hiển thị partial object state trong toString khi object đang được khởi tạo dở như thế nào?
Bạn phân tích vì sao toString của một object được dùng trong logging phải xem xét concurrency và mutable state ra sao?
Bạn sẽ thiết kế output của toString giúp phân biệt phiên bản và business ID mà không coi nó là key machine parsing ra sao?
Bạn mô tả ưu điểm và giới hạn của generated toString từ record trong việc xử lý component chứa secrets như thế nào?
Bạn sẽ quyết định khi nào override toString của record để che bớt dữ liệu thay vì dùng mặc định như thế nào?
Bạn sẽ viết unit test kiểm tra toString không ném exception khi fields nullable hoặc collection rỗng như thế nào?
Bạn phân tích vì sao so sánh chính xác output toString trong nhiều tests có thể làm refactoring khó hơn ra sao?
Bạn sẽ xác định trường hợp toString có thể gây log injection nếu field chứa newline hoặc control characters như thế nào?
Bạn sẽ phân biệt escape dữ liệu tại toString và escape tại structured logging encoder theo trách nhiệm nào?
Bạn sẽ kiểm thử toString không truy cập dữ liệu nhạy cảm hoặc thay đổi trạng thái object khi được gọi như thế nào?
Bạn giải thích immutable object là gì và tại sao tính bất biến giúp equality/hashCode ổn định như thế nào?
Bạn sẽ thiết kế private final fields cho value object nhưng vẫn xem xét mutable nested objects ra sao?
Bạn phân tích vì sao final reference tới một List không có nghĩa nội dung List là bất biến như thế nào?
Bạn sẽ thực hiện defensive copy trong constructor và accessor khi class có field kiểu byte array như thế nào?
Bạn phân biệt List.copyOf với Collections.unmodifiableList về snapshot và khả năng bị thay đổi qua nguồn gốc như thế nào?
Bạn sẽ chọn canonicalization đầu vào trước khi construction để giữ equality của chuỗi không phân biệt case như thế nào?
Bạn mô tả vì sao normalized representation nên tham gia cả equals và hashCode theo cùng quy tắc như thế nào?
Bạn sẽ tránh dùng transient runtime cache fields trong equality khi value object cần logical stability như thế nào?
Bạn phân tích rủi ro lazy initialization thay đổi một field thuộc equality khi object đã vào Set như thế nào?
Bạn sẽ thiết kế method withValue tạo instance mới thay vì sửa một field tham gia hashCode như thế nào?
Bạn phân biệt immutable value type với mutable entity trong việc sử dụng làm collection key ra sao?
Bạn sẽ dùng constructor validation để bảo đảm trạng thái bất hợp lệ không tồn tại ở những object được so sánh như thế nào?
Bạn mô tả value object có nested List các phần tử mutable phải làm gì để đạt deep immutability ra sao?
Bạn sẽ kiểm tra escape của mutable collections qua getter có thể phá equals/hashCode contract theo cách nào?
Bạn phân tích vì sao copy-on-write giúp thay value trong một immutable data structure mà không làm thay đổi key cũ như thế nào?
Bạn sẽ lựa chọn BigDecimal normalized amount trong value object có ý nghĩa nghiệp vụ cụ thể theo cách nào?
Bạn phân biệt bảo đảm safe publication của immutable object với việc equals có thread-safe side effects như thế nào?
Bạn sẽ thiết kế một monetary value class tuân thủ equals/hashCode mà không phụ thuộc locale khi format như thế nào?
Bạn mô tả rủi ro giữ reference tới mutable Date trong object có hashCode cache như thế nào?
Bạn sẽ đánh giá trade-off giữa immutable map keys và chi phí tạo objects mới trong workload lớn ra sao?
Bạn phân tích khi nào dùng record với immutable components giúp tránh viết thủ công equality boilerplate như thế nào?
Bạn sẽ kiểm thử mutation của input sau construction để xác nhận immutable class không lộ state ra sao?
Bạn sẽ thiết kế property-based test đảm bảo hashCode không đổi khi object bất biến được quan sát nhiều lần như thế nào?
Bạn giải thích Comparable<T> biểu diễn natural ordering của một class trong Java như thế nào?
Bạn sẽ cài đặt compareTo cho một value object dựa trên thứ tự của những thuộc tính nào?
Bạn phân biệt kết quả âm, bằng không và dương của compareTo với hiệu số giá trị trả về cụ thể như thế nào?
Bạn sẽ giải thích vì sao không nên trả phép trừ hai int trong compareTo khi có nguy cơ overflow ra sao?
Bạn sẽ sử dụng Integer.compare hoặc Long.compare để sắp thứ tự primitive fields an toàn như thế nào?
Bạn mô tả String.compareTo khác String.equals về vai trò ordering và equality ra sao?
Bạn sẽ quyết định natural ordering có nên nhất quán với equals trong một public value class theo điều kiện nào?
Bạn phân tích vì sao compareTo trả zero cho hai objects mà equals trả false gây hành vi bất ngờ trong sorted collections ra sao?
Bạn sẽ viết compareTo nhiều tầng bằng primary key và secondary key để tránh tie không chủ ý như thế nào?
Bạn phân biệt sorting theo ID và sorting theo display name khi chỉ có một natural ordering được khai báo ra sao?
Bạn sẽ chọn một Comparable implementation hay Comparator truyền ngoài nếu nhiều tiêu chí sắp xếp cùng hợp lệ như thế nào?
Bạn mô tả tính antisymmetry của dấu compareTo giữa x và y theo hợp đồng nào?
Bạn sẽ kiểm tra transitivity của compareTo qua ba đối tượng có ordering liên quan như thế nào?
Bạn phân tích vì sao comparator/compareTo không transitive có thể làm sorting algorithm báo lỗi hoặc trả kết quả sai ra sao?
Bạn sẽ đánh giá quy tắc khi compareTo trả zero so với những đối tượng thứ ba phải có cùng dấu thứ tự như thế nào?
Bạn mô tả xử lý null khi compareTo nhận null và sự khác nhau với equals(null) như thế nào?
Bạn sẽ thiết kế natural ordering cho class không thể so sánh có nghĩa giữa hai currency khác nhau theo lựa chọn nào?
Bạn phân tích rủi ro compareTo phụ thuộc clock hoặc biến cấu hình mutable làm sorted collection không ổn định như thế nào?
Bạn sẽ lựa chọn so sánh BigDecimal bằng compareTo hoặc equals theo ngữ nghĩa amount và scale ra sao?
Bạn mô tả vì sao BigDecimal có natural ordering không hoàn toàn nhất quán với equals theo representation như thế nào?
Bạn sẽ kiểm tra compareTo của một record có thứ tự field hợp lý với equals do record tự sinh như thế nào?
Bạn phân biệt Comparable và Comparator trong cách TreeSet chọn chính sách trùng lặp phần tử ra sao?
Bạn sẽ tạo unit tests cho compareTo với min/max primitive values để phát hiện overflow như thế nào?
Bạn sẽ xây test random triples kiểm tra ordering transitivity thay vì chỉ thử cặp đối tượng ra sao?
Bạn phân tích vì sao không nên ép một class implements Comparable khi domain không có natural order rõ ràng như thế nào?
Bạn sẽ xác định lúc nào compareTo có thể ném ClassCastException khi raw Comparable hoặc generic type bị dùng sai ra sao?
Bạn giải thích Comparator<T> cho phép khai báo nhiều thứ tự bên ngoài class khác Comparable như thế nào?
Bạn sẽ sử dụng Comparator.comparing trích key bằng method reference khi sắp xếp objects ra sao?
Bạn mô tả Comparator.comparingInt và comparingLong tránh boxing khi dùng primitive key như thế nào?
Bạn sẽ dùng thenComparing để bổ sung tie-breaker khi nhiều objects cùng primary sort key như thế nào?
Bạn phân biệt Comparator.reverseOrder với Comparator.reversed trên một comparator có sẵn như thế nào?
Bạn sẽ sử dụng Comparator.nullsFirst và nullsLast để định nghĩa thứ tự của nullable values như thế nào?
Bạn phân tích vì sao dùng Comparator.comparing với extractor có thể null sẽ cần null-aware comparator như thế nào?
Bạn sẽ kết hợp comparing và thenComparing theo tên, ngày sinh và ID để có total ordering ra sao?
Bạn mô tả Comparator.naturalOrder yêu cầu type có Comparable như thế nào?
Bạn phân biệt comparator trả zero với equals true theo tác động tới TreeSet ra sao?
Bạn sẽ đánh giá lựa chọn Comparator.comparing(x -> x.getName().toLowerCase()) có thể thay đổi theo locale ra sao?
Bạn sẽ cân nhắc Collator khi sắp xếp chuỗi theo ngôn ngữ tự nhiên nhưng vẫn kiểm tra tính nhất quán như thế nào?
Bạn phân tích vì sao sắp xếp theo lowercase không có tie-breaker có thể coi hai strings khác nhau là bằng nhau trong TreeSet ra sao?
Bạn sẽ tạo comparator có thứ tự ổn định dựa trên normalized name rồi original ID như thế nào?
Bạn mô tả Comparator.comparingDouble xử lý NaN và signed zero theo quy tắc so sánh nào?
Bạn sẽ phân biệt comparing các numbers qua Double.compare với phép trừ và ép kiểu về int theo nguy cơ nào?
Bạn sẽ thiết kế comparator sắp xếp giá trị âm/dương mà không làm mất thông tin vì overflow như thế nào?
Bạn phân tích vì sao comparator giữ tham chiếu tới mutable external configuration có thể làm thứ tự thay đổi sau insertion ra sao?
Bạn sẽ xác định có nên serialize Comparator nếu một dữ liệu sort order cần được tái tạo qua nhiều processes như thế nào?
Bạn mô tả tác động của Comparator không nhất quán khi được dùng trong Collections.sort như thế nào?
Bạn sẽ kiểm thử comparator giữ antisymmetry, transitivity và khả năng so sánh với các giá trị biên ra sao?
Bạn phân biệt stable sorting với việc comparator tạo ra total order cho mọi phần tử như thế nào?
Bạn sẽ giải thích Collections.sort và List.sort có giữ relative order của các phần tử compare bằng zero theo contract nào?
Bạn sẽ dùng Stream.sorted(comparator) khi cần trả danh sách mới mà không mutate source collection như thế nào?
Bạn phân tích vì sao một comparator có side effects sẽ gây lỗi khó đoán khi sort engine gọi nhiều lần như thế nào?
Bạn sẽ xác định khi nào cần comparator kết hợp business priority và secondary timestamp theo kết quả nào?
Bạn mô tả cách Comparator.nullsLast hoạt động khi comparator được bọc lại qua reversed như thế nào?
Bạn sẽ dùng Comparator.comparing kết hợp Optional nullable attribute theo chính sách nào?
Bạn phân tích chi phí gọi key extractor đắt trong comparator và lựa chọn precompute sort keys như thế nào?
Bạn sẽ test sắp xếp dữ liệu có tên Unicode, dấu tiếng Việt và ký tự viết hoa thường theo chính sách locale nào?
Bạn giải thích TreeSet dựa vào comparator hoặc natural ordering để xác định trùng lặp như thế nào?
Bạn sẽ so sánh HashSet và TreeSet trong cách nhận biết hai phần tử có giá trị tương đương ra sao?
Bạn mô tả vì sao TreeSet có thể từ chối phần tử mới nếu compare trả zero dù equals trả false như thế nào?
Bạn sẽ giải thích TreeMap dùng comparator so sánh keys thay vì hashCode khi thao tác get/put như thế nào?
Bạn phân tích vì sao TreeMap có thể ghi đè value của key khác theo equals nếu comparator coi chúng bằng nhau như thế nào?
Bạn sẽ xác định khi nào cần tie-breaker để không mất phần tử có cùng tên nhưng ID khác trong TreeSet ra sao?
Bạn mô tả NavigableSet.lower, floor, ceiling và higher phụ thuộc ordering của comparator như thế nào?
Bạn sẽ thiết kế khoảng subSet hoặc subMap với boundaries phù hợp theo business comparison contract ra sao?
Bạn phân biệt HashMap key lookup với TreeMap lookup về yêu cầu stable hash và stable ordering ra sao?
Bạn sẽ phân tích việc mutate field dùng trong Comparator sau khi insert vào TreeSet có thể phá cấu trúc ordering ra sao?
Bạn mô tả vì sao SortedSet.contains có thể trả kết quả khác HashSet.contains cho objects không có ordering consistent with equals như thế nào?
Bạn sẽ chọn LinkedHashSet khi cần insertion order nhưng muốn giữ equality qua equals/hashCode như thế nào?
Bạn phân biệt Set.of behavior đối với duplicate elements và null với HashSet theo contract nào?
Bạn sẽ đánh giá Arrays.sort và Collections.sort trong xử lý compareTo hoặc Comparator không hợp lệ ra sao?
Bạn mô tả PriorityQueue dùng comparator để ưu tiên phần tử nhưng không giữ iteration order đã được sắp toàn phần như thế nào?
Bạn sẽ kiểm tra PriorityQueue chứa nhiều phần tử compare bằng zero nhưng equals khác nhau theo semantics nào?
Bạn phân tích vì sao dùng reverse comparator trong TreeSet có thể đảo việc xác định first/last mà không đổi equality định nghĩa bởi comparator ra sao?
Bạn sẽ thiết kế test đối chiếu HashSet và TreeSet trên cùng domain objects để phát hiện inconsistent comparison như thế nào?
Bạn sẽ kiểm thử TreeMap key có null với natural ordering và comparator nullsFirst theo hai cấu hình ra sao?
Bạn mô tả tác động của comparator không stable khi cùng object thay đổi state giữa các lần search như thế nào?
Bạn sẽ giải thích tại sao TreeSet và TreeMap là sorted structures nhưng không thay thế mọi use case của hash collections như thế nào?
Bạn phân tích vì sao comparator trả zero cho nhiều phần tử giúp nhóm equivalence classes nhưng có thể vi phạm yêu cầu unique identity ra sao?
Bạn sẽ định nghĩa ordering của một composite key để giữ uniqueness cả nhóm và ID ra sao?
Bạn sẽ xác định khi nào cần giữ nhiều giá trị cùng sort key bằng Map<SortKey,List<Value>> thay vì TreeSet ra sao?
Bạn phân biệt Objects.equals với gọi a.equals(b) khi a có thể null như thế nào?
Bạn sẽ dùng Objects.deepEquals khi nested arrays được chứa trong object theo semantics nào?
Bạn mô tả Objects.hashCode và Objects.hash khác nhau khi tính hash một hoặc nhiều fields như thế nào?
Bạn sẽ xác định khi nào Arrays.deepToString phù hợp hơn Arrays.toString đối với mảng đa chiều ra sao?
Bạn phân tích vì sao Objects.toString có fallback không thể thay thế quy tắc che dữ liệu nhạy cảm như thế nào?
Bạn sẽ sử dụng Arrays.equals cho field byte[] thay vì gọi Object.equals trực tiếp theo mục đích nào?
Bạn mô tả record tự cung cấp equals, hashCode và toString từ declared components theo hợp đồng nào?
Bạn sẽ đánh giá record components chứa mutable arrays ảnh hưởng value equality và toString generated ra sao?
Bạn phân tích vì sao record shallow immutability chưa đủ bảo vệ hash-based collection khi nested state thay đổi như thế nào?
Bạn sẽ dùng compact constructor của record để defensive-copy List trước khi lưu trong component ra sao?
Bạn sẽ quyết định có override accessor của record trả defensive copy để ngăn mutation từ bên ngoài như thế nào?
Bạn mô tả vì sao record equality so sánh arrays theo reference semantics và cách thiết kế wrapper phù hợp như thế nào?
Bạn sẽ lựa chọn record hay class thường khi business equality phải bỏ qua một số stored fields như thế nào?
Bạn phân tích nguy cơ override equals của record mà không duy trì consistency với generated hashCode như thế nào?
Bạn sẽ đánh giá việc đổi record component có thể thay đổi contract equals/hashCode của một public API ra sao?
Bạn mô tả enum có identity/equality semantics phù hợp cho finite constants và tương tác với EnumMap/EnumSet như thế nào?
Bạn sẽ xác định khi nào EnumMap thích hợp hơn HashMap cho keys là một enum type như thế nào?
Bạn phân biệt Objects.requireNonNull dùng cho validation với Objects.equals dùng cho comparison theo trách nhiệm nào?
Bạn sẽ giải thích vì sao Objects.compare(a,b,comparator) có thể trả zero ngay khi hai references giống nhau theo contract nào?
Bạn phân tích tác động của việc comparator không thể so sánh null nhưng Objects.compare được gọi với các reference nullable ra sao?
Bạn sẽ xây một consistency checklist cho equals/hashCode/toString/compareTo khi thay đổi fields của một class như thế nào?
Bạn phân biệt test bằng vài ví dụ cụ thể với property-based testing cho những contract toán học của equality và ordering như thế nào?
Bạn sẽ lựa chọn equals verifier hoặc thư viện kiểm tra contract trong test suite nhưng vẫn kiểm tra domain semantics thế nào?
Bạn mô tả cách generated equals/hashCode từ IDE hoặc annotation processing có thể chọn nhầm mutable fields như thế nào?
Bạn sẽ xây unit tests cho reflexivity của equals với nhiều instances và cả object chứa null fields như thế nào?
Bạn sẽ thiết kế test symmetry của equals giữa superclass và subclass trong hierarchy có field mở rộng ra sao?
Bạn mô tả cách property-based test với ba objects có thể tìm transitivity violation của equals như thế nào?
Bạn sẽ kiểm thử equals consistency trước và sau những thao tác không làm thay đổi logical identity của object ra sao?
Bạn phân tích vì sao equality test không thể chỉ dựa trên expected hashCode giống nhau mà bỏ kiểm tra fields như thế nào?
Bạn sẽ xác nhận hashCode contract khi hai objects equals true nhưng được tạo qua paths khác nhau ra sao?
Bạn mô tả cách test HashMap.get với key mới có value tương đương sau khi put key ban đầu như thế nào?
Bạn sẽ thử biến đổi một field tham gia hashCode sau khi insert và phân tích kết quả HashSet.contains ra sao?
Bạn sẽ kiểm thử HashSet không mất hoặc nhân đôi entries khi equals/hashCode tuân thủ hợp đồng như thế nào?
Bạn phân tích vì sao random test samples cần thêm edge cases null, duplicate và hash collisions ra sao?
Bạn sẽ thiết kế test comparison với Integer.MIN_VALUE và Integer.MAX_VALUE để phát hiện overflow khi compareTo ra sao?
Bạn sẽ dùng random triples kiểm tra transitivity của Comparator với nhiều tổ hợp key ra sao?
Bạn mô tả cách kiểm tra sign consistency của comparator(a,b) và comparator(b,a) như thế nào?
Bạn sẽ kiểm tra comparator trả zero có phù hợp với equality và business uniqueness khi dùng TreeSet ra sao?
Bạn phân tích vì sao test sắp xếp chỉ so sánh output sequence có thể không phát hiện comparator không transitive ra sao?
Bạn sẽ kiểm tra toString không để lộ password hoặc token qua nested data objects như thế nào?
Bạn sẽ thiết kế test toString với circular reference để bảo đảm không đệ quy vô hạn ra sao?
Bạn mô tả cách kiểm tra equals không gọi network hoặc lazy loaded DB dưới các fixtures khác nhau như thế nào?
Bạn sẽ phân biệt lỗi functional regression với thay đổi contract dự kiến khi cập nhật generated equals của record ra sao?
Bạn sẽ định nghĩa test cho value object đã được canonicalize để tránh khác biệt Unicode normalization ngoài ý muốn ra sao?
Bạn phân tích vì sao snapshot test của toString có thể dễ vỡ khi field order hoặc formatting thay đổi ra sao?
Bạn sẽ dùng mutation testing để kiểm tra test suite có phát hiện khi bỏ một field khỏi equals hoặc hashCode ra sao?
Bạn mô tả cách thiết kế benchmark hash collision rate mà không coi performance measurement là kiểm chứng correctness như thế nào?
Bạn sẽ rà soát các collections dùng object keys khi đề xuất thay đổi equality trong một public library theo trình tự nào?
Nếu hai đối tượng bằng nhau theo equals nhưng HashSet vẫn chứa cả hai, bạn sẽ kiểm tra hashCode và symmetry như thế nào?
Nếu HashMap.get trả null sau khi key được sửa một field, bạn sẽ phân tích hash bucket và mutation của key ra sao?
Nếu một class hashCode luôn trả 1 khiến truy vấn chậm, bạn sẽ kiểm tra contract và cải thiện distribution như thế nào?
Nếu một subclass chỉ so sánh thêm field color khiến equals với superclass không đối xứng, bạn sẽ sửa hierarchy ra sao?
Nếu transient entity có id null bị coi bằng nhau với entity khác chưa persist, bạn sẽ thiết kế equality lại như thế nào?
Nếu một proxy subclass khiến getClass khác entity class trong equals, bạn sẽ phân tích contract trước khi đổi instanceof ra sao?
Nếu record chứa byte[] và hai arrays có nội dung giống nhau nhưng equals false, bạn sẽ điều chỉnh value model như thế nào?
Nếu object chứa List được đặt làm HashMap key rồi caller sửa List, bạn sẽ thêm defensive copy ở ranh giới nào?
Nếu BigDecimal 1.0 và 1.00 được HashSet coi khác nhau còn TreeSet coi giống nhau, bạn sẽ giải thích equals/compareTo ra sao?
Nếu TreeSet mất một customer có cùng tên với customer khác, bạn sẽ thêm tie-breaker vào comparator theo yêu cầu nào?
Nếu compareTo dùng phép trừ khiến sort sai ở giá trị biên int, bạn sẽ sửa bằng comparator primitives như thế nào?
Nếu Comparator phụ thuộc timezone hoặc locale mặc định, bạn sẽ cố định quy tắc so sánh cho các lần chạy như thế nào?
Nếu một TreeMap không tìm được key sau khi field dùng trong Comparator đổi giá trị, bạn sẽ chẩn đoán và sửa data model ra sao?
Nếu toString đệ quy qua parent-child references gây StackOverflowError, bạn sẽ thiết kế output có giới hạn như thế nào?
Nếu toString vô tình chứa access token khi log một object, bạn sẽ rà soát call sites và redaction theo cách nào?
Nếu một bộ equals test luôn PASS nhưng production HashMap bị lookup miss, bạn sẽ bổ sung test key lifecycle và normalization như thế nào?
Nếu record generated hashCode thay đổi sau khi component List bị mutate, bạn sẽ kiểm soát ownership của list ra sao?
Nếu equals dùng String.equalsIgnoreCase còn hashCode dùng String.hashCode, bạn sẽ xây cùng quy tắc chuẩn hóa như thế nào?
Nếu hai keys có cùng hashCode nhưng không equals, bạn sẽ chứng minh HashMap vẫn lưu riêng chúng theo contract nào?
Nếu một class có compareTo bằng zero cho hai keys khác nhau nhưng business muốn giữ cả hai, bạn sẽ chọn cấu trúc dữ liệu nào?
Nếu gọi Collections.sort ném IllegalArgumentException liên quan comparison contract, bạn sẽ kiểm tra transitivity và consistency ra sao?
Nếu sửa equals của một public class làm kết quả dedup thay đổi, bạn sẽ đánh giá migration impact với caches và persistence như thế nào?
Nếu cần tạo value class Money với currency, amount và bất biến sâu, bạn sẽ thiết kế equals, hashCode, toString và ordering như thế nào?
Nếu domain entity có identifier ổn định sau persist nhưng null trước persist, bạn sẽ lựa chọn equality strategy và test transitions ra sao?
Nếu phải đánh giá một class trước khi dùng làm HashMap key và TreeSet element, bạn sẽ kiểm tra hợp đồng Object và ordering theo checklist nào?
