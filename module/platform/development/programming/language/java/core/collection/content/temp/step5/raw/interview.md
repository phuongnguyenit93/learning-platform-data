Bạn phân biệt vai trò và hợp đồng của `Collection`, `List`, `Set`, `Queue` và `Map` trong Java Collections Framework như thế nào?
Bạn xác định khi nào một yêu cầu nghiệp vụ cần `List` thay vì `Set` hoặc `Map` dựa trên tính duy nhất và cách truy xuất ra sao?
Bạn giải thích sự khác nhau giữa interface, implementation và utility class trong Java Collections Framework như thế nào?
Bạn phân biệt các thao tác tùy chọn của `Collection` và cách một implementation báo không hỗ trợ thao tác đó ra sao?
Bạn lựa chọn cấu trúc dữ liệu dựa trên chi phí thêm, xóa, tìm kiếm, duyệt và bộ nhớ bằng cách nào?
Bạn đánh giá ảnh hưởng của kích thước dữ liệu và mẫu truy cập thực tế khi so sánh độ phức tạp trung bình với trường hợp xấu nhất ra sao?
Bạn sử dụng generics trong `Collection` để ngăn lỗi kiểu dữ liệu khi biên dịch và nhận diện giới hạn của type erasure như thế nào?
Bạn phân biệt `Collection` với `Collections` và `Arrays` trong những tình huống thao tác dữ liệu phổ biến ra sao?
Bạn kiểm tra ngữ nghĩa của `equals` và `hashCode` đối với phần tử trước khi đưa vào một collection dựa trên hashing như thế nào?
Bạn giải thích vì sao hai đối tượng bằng nhau theo `equals` cần có cùng giá trị `hashCode` và hệ quả khi vi phạm ra sao?
Bạn thiết kế `equals` và `hashCode` cho entity có trường thay đổi được khi entity được lưu trong `HashSet` như thế nào?
Bạn chẩn đoán một phần tử vẫn xuất hiện khi duyệt `HashSet` nhưng `contains` lại trả về false sau khi cập nhật thuộc tính như thế nào?
Bạn phân biệt tham chiếu đối tượng, equality theo giá trị và identity khi chọn collection hoặc cách lưu khóa ra sao?
Bạn kiểm chứng hai `List` có cùng phần tử nhưng khác thứ tự được so sánh bằng nhau theo hợp đồng nào?
Bạn giải thích ngữ nghĩa so sánh hai `Set` chứa cùng phần tử nhưng được thêm theo thứ tự khác nhau như thế nào?
Bạn kiểm tra tính nhất quán giữa `compareTo`, `Comparator` và `equals` trước khi sử dụng collection có thứ tự ra sao?
Bạn đánh giá khả năng lưu `null` và hành vi tương ứng giữa các implementation của `List`, `Set`, `Map` và `Queue` như thế nào?
Bạn lựa chọn `ArrayList` hay `LinkedList` khi ứng dụng vừa truy cập ngẫu nhiên vừa chèn hoặc xóa phần tử ra sao?
Bạn phân tích chi phí truy cập phần tử tại chỉ số bất kỳ trong `ArrayList` và `LinkedList` theo cấu trúc nội bộ như thế nào?
Bạn giải thích khả năng mở rộng mảng nền của `ArrayList` và tác động của việc thêm liên tiếp nhiều phần tử như thế nào?
Bạn quyết định khi nào nên đặt dung lượng ban đầu cho `ArrayList` hoặc dùng `ensureCapacity` để giảm cấp phát lại ra sao?
Bạn kiểm tra ảnh hưởng của `trimToSize` lên dung lượng và chi phí mở rộng sau đó của `ArrayList` như thế nào?
Bạn phân biệt `List.add(index, element)` với `List.set(index, element)` về thay đổi kích thước và vị trí phần tử ra sao?
Bạn xử lý sự khác nhau giữa `remove(int)` và `remove(Object)` khi `List` chứa `Integer` như thế nào?
Bạn xác định cách xóa phần tử theo điều kiện bằng `removeIf` mà không phá vỡ quy tắc iteration như thế nào?
Bạn giải thích quan hệ giữa `subList` và danh sách gốc khi một trong hai bị thay đổi cấu trúc ra sao?
Bạn tạo một bản sao độc lập của một đoạn `List` để tránh các tác động không mong muốn từ `subList` như thế nào?
Bạn so sánh `ArrayList` và `LinkedList` về bộ nhớ mỗi phần tử, khả năng tận dụng cache CPU và chi phí duyệt ra sao?
Bạn giải thích khi nào `ListIterator` phù hợp hơn `Iterator` để duyệt hai chiều và chỉnh sửa phần tử như thế nào?
Bạn phân biệt thay đổi phần tử bằng `ListIterator.set` với thao tác thêm hoặc xóa trong quá trình duyệt ra sao?
Bạn đánh giá sự khác nhau giữa `for-each`, vòng lặp theo chỉ số và `Iterator` trên các loại `List` như thế nào?
Bạn chẩn đoán `ConcurrentModificationException` trong vòng lặp ngay cả khi chương trình chỉ có một luồng như thế nào?
Bạn phân biệt cơ chế fail-fast với cơ chế bảo đảm an toàn luồng khi duyệt một collection ra sao?
Bạn giải thích những giới hạn khi dựa vào fail-fast iterator để phát hiện mọi thay đổi đồng thời như thế nào?
Bạn thiết kế thao tác duyệt và xóa phần tử an toàn bằng `Iterator.remove` khi xử lý một collection có thể thay đổi như thế nào?
Bạn lựa chọn `HashSet`, `LinkedHashSet` hoặc `TreeSet` cho yêu cầu duy nhất, giữ thứ tự chèn hoặc sắp xếp ra sao?
Bạn mô tả cách `HashSet` sử dụng cơ chế của `HashMap` để bảo đảm phần tử duy nhất như thế nào?
Bạn phân tích tác động của hash collision đối với chi phí thêm và tra cứu trong `HashSet` như thế nào?
Bạn giải thích các điều kiện để `HashMap` chuyển một bucket nhiều phần tử thành cấu trúc cây và ý nghĩa hiệu năng ra sao?
Bạn chọn initial capacity và load factor cho `HashMap` hoặc `HashSet` trong một luồng dữ liệu có kích thước dự kiến như thế nào?
Bạn đánh giá chi phí resize và rehash của `HashMap` khi số lượng phần tử tăng nhanh ra sao?
Bạn chẩn đoán vì sao một `HashMap` không tìm được giá trị sau khi thuộc tính dùng tạo `hashCode` của khóa bị sửa như thế nào?
Bạn sử dụng khóa bất biến cho `HashMap` và đánh giá rủi ro khi dùng array hoặc collection mutable làm khóa ra sao?
Bạn phân biệt trường hợp khóa đã tồn tại với trường hợp giá trị ánh xạ là `null` khi dùng `containsKey` và `get` như thế nào?
Bạn lựa chọn `getOrDefault`, `putIfAbsent`, `computeIfAbsent` và `merge` theo mục đích cập nhật ánh xạ ra sao?
Bạn thiết kế phép đếm tần suất bằng `Map.merge` và kiểm soát trường hợp hàm kết hợp tạo giá trị `null` như thế nào?
Bạn giải thích sự khác nhau giữa `computeIfPresent` và `compute` khi khóa vắng mặt hoặc đã ánh xạ sang `null` như thế nào?
Bạn đánh giá rủi ro khi hàm tính toán dùng trong `Map.computeIfAbsent` có side effect hoặc thay đổi lại chính map đó ra sao?
Bạn sử dụng `entrySet`, `keySet` và `values` để duyệt `Map` hiệu quả, đồng thời kiểm soát thay đổi qua collection view như thế nào?
Bạn phân biệt `Map.Entry.setValue` và sửa map trực tiếp trong khi đang duyệt `entrySet` về tính hợp lệ và hiệu quả ra sao?
Bạn giải thích vì sao thứ tự iteration của `HashMap` không nên được coi là hợp đồng thứ tự dữ liệu như thế nào?
Bạn cấu hình `LinkedHashMap` theo thứ tự truy cập để xây dựng bộ đệm LRU và đánh giá giới hạn khi dùng đa luồng ra sao?
Bạn phân biệt insertion order và access order của `LinkedHashMap` khi một khóa được đọc hoặc ghi lại như thế nào?
Bạn chọn `TreeMap` khi cần tra cứu theo khoảng khóa hoặc phần tử gần nhất bằng những tiêu chí nào?
Bạn sử dụng `NavigableMap.floorEntry`, `ceilingEntry` và `higherEntry` để xử lý truy vấn cận trên hoặc cận dưới như thế nào?
Bạn giải thích đặc điểm của `headMap`, `tailMap` và `subMap` khi thao tác trên view theo khoảng của `TreeMap` ra sao?
Bạn chẩn đoán phần tử bị xem là trùng trong `TreeSet` dù hai đối tượng không bằng nhau theo `equals` như thế nào?
Bạn xây dựng `Comparator` cho nhiều tiêu chí sắp xếp và xử lý giá trị `null` khi yêu cầu nghiệp vụ cho phép ra sao?
Bạn kiểm tra tính bắc cầu và đối xứng dấu của một `Comparator` để tránh hành vi sai trong sorted collection như thế nào?
Bạn phân biệt thứ tự tự nhiên qua `Comparable` với thứ tự truyền vào bằng `Comparator` và khi nào nên chọn mỗi cách ra sao?
Bạn dùng `NavigableSet.lower`, `floor`, `ceiling` và `higher` để tìm phần tử gần một mốc đã cho như thế nào?
Bạn xác định cách sử dụng `EnumSet` và `EnumMap` khi miền khóa hoặc phần tử là một enum cố định ra sao?
Bạn đánh giá sự khác nhau giữa `IdentityHashMap` và `HashMap` về tiêu chí so sánh khóa và trường hợp sử dụng như thế nào?
Bạn sử dụng `WeakHashMap` trong bộ nhớ đệm và kiểm chứng thời điểm entry có thể biến mất do garbage collection ra sao?
Bạn phân biệt `PriorityQueue` với `TreeSet` khi yêu cầu xử lý theo độ ưu tiên có thể chứa phần tử trùng nhau như thế nào?
Bạn giải thích vai trò của cấu trúc heap trong `PriorityQueue` và giới hạn thứ tự khi duyệt bằng iterator ra sao?
Bạn xác định chiến lược xử lý khi phần tử trong `PriorityQueue` bị sửa trường dùng để so sánh độ ưu tiên như thế nào?
Bạn lựa chọn `ArrayDeque` cho ngăn xếp hoặc hàng đợi hai đầu thay vì `Stack` hoặc `LinkedList` dựa trên tiêu chí nào?
Bạn phân biệt `add`, `offer`, `remove`, `poll`, `element` và `peek` của `Queue` khi đầy hoặc rỗng như thế nào?
Bạn sử dụng `Deque.addFirst`, `offerLast`, `pollFirst` và `peekLast` để xây dựng hàng đợi hai đầu ra sao?
Bạn giải thích vì sao xử lý giá trị `null` trong queue có thể làm mơ hồ ý nghĩa của `poll` như thế nào?
Bạn dùng `Collections.binarySearch` trên danh sách đã sắp xếp và xử lý kết quả khi phần tử không tồn tại như thế nào?
Bạn phân biệt sort in-place bằng `List.sort` với việc tạo dữ liệu mới có thứ tự trong một quy trình xử lý ra sao?
Bạn đánh giá yêu cầu về tính ổn định của thuật toán sắp xếp `List` khi có nhiều phần tử cùng khóa so sánh như thế nào?
Bạn lựa chọn `Collections.shuffle`, `reverse`, `rotate` hoặc `swap` để biến đổi một danh sách với các ràng buộc nào?
Bạn phân biệt danh sách fixed-size trả về từ `Arrays.asList` với một `ArrayList` có thể tăng giảm kích thước như thế nào?
Bạn giải thích mối liên hệ giữa mảng nguồn và danh sách `Arrays.asList` khi một bên thay đổi phần tử ra sao?
Bạn so sánh `List.of`, `Set.of` và `Map.of` về giới hạn giá trị `null`, phần tử trùng và khả năng chỉnh sửa như thế nào?
Bạn phân biệt collection bất biến thực sự với unmodifiable view được tạo bởi `Collections.unmodifiableList` như thế nào?
Bạn kiểm chứng thay đổi từ collection gốc có thể được quan sát qua unmodifiable view mà không thể chỉnh sửa qua view như thế nào?
Bạn lựa chọn `List.copyOf`, `Set.copyOf` hoặc `Map.copyOf` để tạo snapshot và xử lý phần tử mutable ra sao?
Bạn giải thích vì sao không thể suy ra mọi đối tượng bên trong một collection là bất biến chỉ vì collection không cho thêm hoặc xóa như thế nào?
Bạn sử dụng `Collections.emptyList`, `singletonList` hoặc `nCopies` cho trường hợp dữ liệu cố định theo cách nào?
Bạn thiết kế API trả về collection để bảo vệ trạng thái nội bộ khỏi bị gọi bên ngoài sửa đổi như thế nào?
Bạn phân biệt `Collections.synchronizedList` với collection đồng thời chuyên dụng về khóa và iteration như thế nào?
Bạn tổ chức duyệt một synchronized collection đúng cách khi nhiều luồng có thể cập nhật nó ra sao?
Bạn lựa chọn `CopyOnWriteArrayList` cho danh sách listener được đọc nhiều và thay đổi ít dựa trên phân tích chi phí nào?
Bạn giải thích vì sao iterator của `CopyOnWriteArrayList` quan sát snapshot và tác động của điều đó đến thao tác xóa như thế nào?
Bạn sử dụng `ConcurrentHashMap` cho một bảng tra cứu đồng thời và giải thích khác biệt với `HashMap` được đồng bộ thủ công ra sao?
Bạn thiết kế phép cập nhật bộ đếm hoặc khởi tạo theo khóa bằng `ConcurrentHashMap.computeIfAbsent` mà tránh hàm tính toán gây nghẽn như thế nào?
Bạn phân biệt ngữ nghĩa của iterator trên `ConcurrentHashMap` với fail-fast iterator của `HashMap` khi cập nhật đồng thời ra sao?
Bạn kiểm chứng các hạn chế đối với khóa và giá trị `null` của `ConcurrentHashMap` trước khi thiết kế API như thế nào?
Bạn quyết định khi nào cần `ConcurrentSkipListMap` thay vì `ConcurrentHashMap` để hỗ trợ thao tác theo khoảng có thứ tự ra sao?
Bạn lựa chọn `BlockingQueue` hay queue không chặn khi thiết kế luồng producer-consumer với cơ chế backpressure như thế nào?
Bạn phân biệt `put`, `take`, `offer` có timeout và `poll` có timeout của `BlockingQueue` trong tình huống quá tải ra sao?
Bạn so sánh `ArrayBlockingQueue`, `LinkedBlockingQueue` và `SynchronousQueue` về dung lượng, truyền giao và áp lực bộ nhớ như thế nào?
Bạn kiểm soát chính sách đóng producer-consumer khi nhiều luồng đang bị chặn trên queue như thế nào?
Bạn xác định khi nào `PriorityBlockingQueue` có thể gây tích tụ dữ liệu do đặc tính dung lượng và xử lý ưu tiên ra sao?
Bạn phân biệt `Deque` thông thường với `ConcurrentLinkedDeque` khi cần thao tác hai đầu trong môi trường đa luồng như thế nào?
Bạn thiết kế biện pháp tránh lỗi check-then-act khi nhiều luồng cùng kiểm tra rồi chỉnh sửa một collection ra sao?
Bạn chọn giữa đồng bộ toàn bộ collection, dùng thao tác atomic của concurrent collection và thiết kế dữ liệu bất biến dựa trên tiêu chí nào?
Bạn giải thích ý nghĩa của wildcard `extends` và `super` trong chữ ký API nhận hoặc trả về collection như thế nào?
Bạn áp dụng nguyên tắc PECS để viết một phương thức sao chép phần tử giữa hai collection với kiểu kế thừa khác nhau ra sao?
Bạn phân biệt `Collection.addAll` với `Collections.addAll` về kiểu tham số và tình huống sử dụng như thế nào?
Bạn đánh giá ảnh hưởng của boxing và unboxing khi lưu số nguyên số lượng lớn trong collection dùng generic như thế nào?
Bạn xử lý vấn đề type safety khi cần tích hợp API legacy trả về raw collection với mã generic hiện đại ra sao?
Bạn kiểm tra sự khác nhau giữa `Stream.toList` và `Collectors.toList` về hợp đồng khả năng chỉnh sửa của kết quả ra sao?
Bạn xử lý trùng khóa khi thu thập stream thành `Map` bằng `Collectors.toMap` như thế nào?
Bạn chọn `groupingBy`, `partitioningBy` hoặc custom collector để gom dữ liệu thành các collection phù hợp ra sao?
Bạn xác định ảnh hưởng của thứ tự encounter order lên kết quả collection khi xử lý parallel stream như thế nào?
Bạn thiết kế `Spliterator` tùy chỉnh cho một collection sao cho mô tả đúng các đặc tính ORDERED, SIZED và DISTINCT ra sao?
Bạn đánh giá chi phí bộ nhớ và tính phù hợp của `HashMap`, `TreeMap` và `ArrayList` khi số phần tử tăng tới hàng triệu như thế nào?
Bạn lập kế hoạch benchmark các thao tác thêm, tìm, xóa và duyệt collection để tránh sai lệch do JIT hoặc dữ liệu thử quá nhỏ ra sao?
Bạn xây dựng bộ kiểm thử hồi quy nhằm phát hiện lỗi equality, ordering, tính bất biến và thao tác đồng thời của một API dựa trên collection như thế nào?
