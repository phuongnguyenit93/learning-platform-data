# Sao chép cây và quản lý việc chia sẻ node có thể thay đổi

Trong Jackson tree model, JsonNode là kiểu nền tảng để biểu diễn một giá trị JSON. ObjectNode và ArrayNode là các container có thể thay đổi: ứng dụng có thể thêm, thay thế hoặc xóa node con sau khi parse. Vì vậy, khi gắn một node vào nhiều cây hoặc truyền cây cho nhiều thành phần, cần hiểu rõ sự khác nhau giữa **chia sẻ tham chiếu**, **sao chép nông** và **sao chép sâu**.

Một biến Java không chứa bản sao của object mà thường chứa tham chiếu đến object đó. Nếu hai biến cùng trỏ đến một ObjectNode, thay đổi qua biến này sẽ được nhìn thấy qua biến kia. Tương tự, nếu cùng một node con được gắn vào hai object cha, cả hai cây có thể cùng quan sát thay đổi bên trong node con đó.

Jackson cung cấp deepCopy() để sao chép đệ quy một cây node. Dùng đúng cách giúp tạo snapshot độc lập, tránh side effect giữa các bước xử lý và giảm rủi ro khi chia sẻ dữ liệu giữa nhiều thành phần.

## 1. Node container có thể thay đổi

Trong Jackson tree model, các kiểu node có vai trò khác nhau:

- JsonNode là kiểu cơ sở để tham chiếu đến mọi loại giá trị JSON.
- ObjectNode biểu diễn JSON object và cho phép thêm, sửa, xóa thuộc tính.
- ArrayNode biểu diễn JSON array và cho phép thêm, thay thế, xóa phần tử.
- Các node giá trị như TextNode, IntNode, BooleanNode và NullNode biểu diễn giá trị đơn.

Ví dụ:

~~~java
ObjectNode profile = mapper.createObjectNode();
profile.put("name", "Linh");
profile.put("active", true);

ObjectNode preferences = profile.putObject("preferences");
preferences.put("theme", "light");

ArrayNode tags = profile.putArray("tags");
tags.add("java");
tags.add("jackson");
~~~

Cây profile có thể tiếp tục được chỉnh sửa:

~~~java
profile.put("active", false);
preferences.put("theme", "dark");
tags.add("serialization");
~~~

ObjectNode và ArrayNode giữ trạng thái có thể thay đổi trong bộ nhớ. Khi nhiều biến cùng tham chiếu đến một container, chúng cùng nhìn thấy trạng thái hiện tại của container đó.

Các node scalar tiêu chuẩn như TextNode, IntNode, BooleanNode và NullNode được thiết kế bất biến. Việc chia sẻ các node giá trị này thường an toàn. Mối quan tâm chính là container node và những wrapper có thể chứa object Java mutable.

## 2. Tham chiếu trong Java: hai biến có thể cùng trỏ đến một node

Xét ví dụ:

~~~java
ObjectNode original = mapper.createObjectNode();
original.put("status", "new");

ObjectNode alias = original;
alias.put("status", "changed");
~~~

Lệnh gán alias = original không tạo object mới. Cả hai biến đều trỏ đến cùng một ObjectNode.

~~~text
original ─────┐
              ├────> ObjectNode { status: "changed" }
alias ────────┘
~~~

Vì vậy, khi gọi alias.put(), dữ liệu được thay đổi trực tiếp trong object mà original cũng tham chiếu đến.

Có thể xác nhận bằng:

~~~java
System.out.println(original.path("status").asText()); // changed
System.out.println(alias.path("status").asText());    // changed
System.out.println(original == alias);                // true
~~~

Đây là aliasing: nhiều tham chiếu cùng truy cập một object. Aliasing không phải lúc nào cũng xấu. Nó giúp tránh sao chép dữ liệu không cần thiết và cho phép nhiều thành phần cùng đọc một cấu trúc. Vấn đề xuất hiện khi một bên sửa node mà bên khác tưởng rằng dữ liệu của mình độc lập.

Nếu cần một bản dữ liệu độc lập, phải tạo bản sao thay vì chỉ gán biến.

## 3. Gắn node con vào nhiều object cũng tạo chia sẻ tham chiếu

Không chỉ việc gán hai biến mới tạo alias. Các API gắn node của Jackson như ObjectNode.set() cũng lưu node được truyền vào trong cây đích.

Ví dụ:

~~~java
ObjectNode sharedSettings = mapper.createObjectNode();
sharedSettings.put("theme", "light");

ObjectNode userView = mapper.createObjectNode();
userView.set("settings", sharedSettings);

ObjectNode adminView = mapper.createObjectNode();
adminView.set("settings", sharedSettings);
~~~

Cả userView và adminView đều tham chiếu đến cùng sharedSettings:

~~~text
userView ── settings ──┐
                       ├──> ObjectNode { theme: "light" }
adminView ─ settings ──┘
~~~

Nếu sửa node con qua một nhánh:

~~~java
((ObjectNode) userView.path("settings")).put("theme", "dark");
~~~

thì đọc qua nhánh còn lại cũng thấy giá trị dark:

~~~java
String theme = adminView.path("settings").path("theme").asText();
// dark
~~~

Điều này xảy ra vì set() không tự động deep copy node con. Nó gắn tham chiếu node vào object cha.

Tương tự, khi thêm một node vào ArrayNode:

~~~java
ObjectNode item = mapper.createObjectNode();
item.put("sku", "BOOK-01");

ArrayNode firstList = mapper.createArrayNode();
firstList.add(item);

ArrayNode secondList = mapper.createArrayNode();
secondList.add(item);
~~~

Hai array đang chứa cùng một ObjectNode. Sửa item qua một array sẽ được nhìn thấy qua array còn lại.

Nếu muốn hai nhánh độc lập, hãy deep copy node con trước khi gắn:

~~~java
userView.set("settings", sharedSettings.deepCopy());
adminView.set("settings", sharedSettings.deepCopy());
~~~

Hoặc tạo hai bản sao từ node nguồn tại thời điểm sử dụng. Cần lựa chọn dựa trên việc các nhánh có thực sự cần chia sẻ cập nhật hay không.

## 4. Sao chép nông và sao chép sâu khác nhau thế nào?

Sao chép nông (shallow copy) tạo container mới nhưng các node con vẫn có thể được chia sẻ. Sao chép sâu (deep copy) tạo bản sao đệ quy cho các container con, để thay đổi cấu trúc ở một cây không ảnh hưởng cây còn lại.

Giả sử cây nguồn:

~~~json
{
  "name": "Linh",
  "settings": {
    "theme": "light",
    "notifications": {
      "email": true
    }
  }
}
~~~

Một shallow copy ở cấp root có thể tạo ObjectNode mới nhưng dùng lại node settings và notifications:

~~~text
source ObjectNode
  |
  +-- name: TextNode
  |
  +-- settings: ObjectNode ── notifications: ObjectNode
              ^
              |
shallow ObjectNode
~~~

Hai root khác nhau, nhưng node settings bên trong vẫn là một object được chia sẻ.

Với deep copy:

~~~text
source ObjectNode
  |
  +-- settings: ObjectNode ── notifications: ObjectNode

deep copy ObjectNode
  |
  +-- settings: ObjectNode ── notifications: ObjectNode
~~~

Mỗi container có thể thay đổi được sao chép riêng. Các giá trị scalar tiêu chuẩn bất biến có thể được tái sử dụng.

Bảng so sánh:

| Đặc điểm | Shallow copy | Deep copy |
|---|---|---|
| Root container | Mới | Mới |
| Container node lồng bên trong | Có thể dùng chung tham chiếu | Được sao chép đệ quy |
| Thay đổi node con | Có thể ảnh hưởng cây nguồn | Không ảnh hưởng container tương ứng ở cây nguồn |
| Chi phí bộ nhớ/thời gian | Thấp hơn | Cao hơn, tỷ lệ với kích thước cây |
| Mục đích | Tạo view hoặc container mới nhưng cố ý chia sẻ nội dung | Tạo snapshot độc lập để chỉnh sửa riêng |

Shallow copy không nhất thiết là lỗi. Nó phù hợp khi chỉ muốn tạo một container mới nhưng vẫn muốn dùng chung một số node con. Tuy nhiên, nếu mục tiêu là độc lập hoàn toàn, shallow copy không đáp ứng yêu cầu.

## 5. Dùng JsonNode.deepCopy() để sao chép sâu

JsonNode cung cấp phương thức deepCopy() để tạo bản sao của node và các container con có thể thay đổi.

Ví dụ:

~~~java
ObjectNode original = mapper.createObjectNode();

ObjectNode settings = original.putObject("settings");
settings.put("theme", "light");

ObjectNode notifications = settings.putObject("notifications");
notifications.put("email", true);

ObjectNode copy = original.deepCopy();
~~~

Sau đó thay đổi bản sao:

~~~java
((ObjectNode) copy.path("settings")).put("theme", "dark");

((ObjectNode) copy.path("settings").path("notifications"))
    .put("email", false);
~~~

Cây nguồn vẫn giữ dữ liệu ban đầu:

~~~java
String originalTheme =
    original.path("settings").path("theme").asText();

boolean originalEmail =
    original.path("settings").path("notifications").path("email").asBoolean();

// originalTheme = "light"
// originalEmail = true
~~~

Có thể dùng deepCopy() với biến kiểu JsonNode:

~~~java
JsonNode source = mapper.readTree(json);
JsonNode snapshot = source.deepCopy();
~~~

Nếu biết root là ObjectNode hoặc ArrayNode, có thể giữ kiểu cụ thể:

~~~java
ObjectNode objectCopy = sourceObject.deepCopy();
ArrayNode arrayCopy = sourceArray.deepCopy();
~~~

Phương thức trả về kiểu node tương ứng nhờ generic type của API. Khi biến nguồn chỉ có kiểu JsonNode, dùng JsonNode cho bản sao sẽ rõ ràng và tránh ép kiểu không cần thiết.

deepCopy() là cách chuẩn để sao chép cây Jackson. Không cần tự duyệt đệ quy mọi object và array nếu chỉ muốn tạo một bản sao độc lập.

## 6. Minh họa sự khác biệt bằng shallow copy và deep copy

Có thể tự tạo shallow copy của ObjectNode bằng cách tạo object mới rồi gắn lại các node con:

~~~java
ObjectNode shallowCopy(ObjectNode source, ObjectMapper mapper) {
    ObjectNode copy = mapper.createObjectNode();

    source.fields().forEachRemaining(entry ->
        copy.set(entry.getKey(), entry.getValue())
    );

    return copy;
}
~~~

Trong ví dụ này, root mới được tạo nhưng entry.getValue() là tham chiếu node con từ source. Các container con vì vậy vẫn có thể được chia sẻ.

So sánh với deep copy:

~~~java
ObjectNode deep = source.deepCopy();
~~~

Ví dụ hoàn chỉnh:

~~~java
ObjectNode source = mapper.createObjectNode();
source.putObject("settings").put("theme", "light");

ObjectNode shallow = shallowCopy(source, mapper);
ObjectNode deep = source.deepCopy();

((ObjectNode) shallow.path("settings")).put("theme", "dark");

String sourceTheme =
    source.path("settings").path("theme").asText();

String deepTheme =
    deep.path("settings").path("theme").asText();

// sourceTheme = "dark"
// deepTheme = "light"
~~~

Kết quả cho thấy shallow copy có root riêng nhưng node settings được dùng chung. deep copy giữ cấu trúc con độc lập.

Một lưu ý: sao chép nông ở đây là ví dụ tự tạo bằng cách gắn lại các node con. Không nên mặc định rằng mọi API copy hoặc collection operation đều có cùng ngữ nghĩa. Hãy kiểm tra hợp đồng của phương thức cụ thể; với Jackson tree model, deepCopy() là lựa chọn rõ ràng khi cần sao chép đệ quy.

## 7. Sao chép ArrayNode và các phần tử lồng nhau

ArrayNode cũng có thể chứa ObjectNode, ArrayNode hoặc node giá trị. Chỉ tạo array mới rồi thêm lại các phần tử hiện có vẫn có thể tạo chia sẻ tham chiếu:

~~~java
ArrayNode source = mapper.createArrayNode();

ObjectNode first = source.addObject();
first.put("sku", "BOOK-01");
first.put("quantity", 2);

ArrayNode shallow = mapper.createArrayNode();

for (JsonNode element : source) {
    shallow.add(element);
}
~~~

Root array shallow là object mới, nhưng phần tử first được dùng lại.

Sửa phần tử qua shallow:

~~~java
((ObjectNode) shallow.get(0)).put("quantity", 9);
~~~

sẽ làm source nhìn thấy quantity bằng 9.

Để tạo bản sao sâu:

~~~java
ArrayNode deep = source.deepCopy();
~~~

Hoặc nếu chỉ cần sao chép một phần tử:

~~~java
JsonNode copiedItem = source.get(0).deepCopy();
~~~

Khi thêm phần tử vào một array khác:

~~~java
ArrayNode independent = mapper.createArrayNode();
independent.add(source.get(0).deepCopy());
~~~

Cách này giữ cấu trúc con độc lập.

Với array gồm các node scalar bất biến, chia sẻ phần tử giá trị thường không tạo side effect vì các node đó không bị sửa. Nhưng nếu array có object hoặc array con, cần sao chép sâu khi muốn tách biệt.

## 8. setAll() không phải là deep copy

ObjectNode có các phương thức setAll() để đưa thuộc tính từ object khác vào object đích:

~~~java
ObjectNode source = mapper.createObjectNode();
source.putObject("preferences").put("theme", "light");

ObjectNode target = mapper.createObjectNode();
target.setAll(source);
~~~

setAll() hữu ích khi muốn gộp các thuộc tính vào object khác. Tuy nhiên, nó không nên được hiểu là thao tác deep copy. Các node con được gắn vào target vẫn có thể là cùng tham chiếu với node con trong source.

Tương tự, khi tự thêm lại từng phần tử của ArrayNode bằng add(node), node được truyền vào vẫn là node hiện có.

Nếu muốn tạo object độc lập, dùng:

~~~java
ObjectNode target = source.deepCopy();
~~~

Nếu muốn gộp các thuộc tính nhưng tách biệt subtree, có thể deep copy trước:

~~~java
ObjectNode target = mapper.createObjectNode();
ObjectNode copiedFields = source.deepCopy();

target.setAll(copiedFields);
~~~

Hoặc sao chép từng node con khi gắn. Mục tiêu là đảm bảo mọi container có thể thay đổi ở cây đích không còn dùng chung với cây nguồn.

## 9. deepCopy() và node giá trị bất biến

Một cây JSON có cả container và node giá trị. Khi deep copy:

- ObjectNode được tạo thành object mới.
- ArrayNode được tạo thành array mới.
- Các container con được sao chép đệ quy.
- Các node giá trị bất biến tiêu chuẩn như TextNode, IntNode, BooleanNode và NullNode có thể được tái sử dụng.

Việc tái sử dụng node scalar là an toàn vì không thể thay đổi nội dung của chúng thông qua API thông thường.

Tuy nhiên, tree model có thể chứa node đặc biệt như POJONode, node tùy biến hoặc wrapper giữ một object Java. Nếu object được bọc là mutable, deepCopy() của cây Jackson không đồng nghĩa với việc clone sâu mọi object Java tùy ý được bọc bên trong.

Ví dụ, nếu một POJONode giữ một ArrayList, việc sao chép cây không nên được xem là cơ chế clone ArrayList đó. Hãy tự xác định chiến lược sao chép cho object Java được bọc hoặc tránh đưa object mutable vào tree nếu cần snapshot độc lập.

Nói cách khác, deepCopy() bảo đảm sao chép cấu trúc node theo hợp đồng của node Jackson. Nó không thay thế một thư viện deep clone tổng quát cho mọi object Java nằm ngoài tree model.

## 10. equals() và == khi kiểm tra bản sao

Sau khi sao chép, hai cây có thể có nội dung giống nhau nhưng là hai object khác nhau.

- == kiểm tra hai biến có tham chiếu đến cùng object hay không.
- equals() trên các node Jackson tiêu chuẩn so sánh cấu trúc và giá trị JSON.

Ví dụ:

~~~java
ObjectNode original = mapper.createObjectNode();
original.putObject("settings").put("theme", "light");

ObjectNode copy = original.deepCopy();

boolean sameReference = original == copy;
boolean sameContent = original.equals(copy);

// sameReference = false
// sameContent = true
~~~

Sau khi thay đổi bản sao:

~~~java
copy.path("settings"); // node này vẫn thuộc bản sao
((ObjectNode) copy.path("settings")).put("theme", "dark");

boolean stillEqual = original.equals(copy); // false
~~~

Trong test, nên kiểm tra cả nội dung và sự độc lập:

~~~java
assertEquals(original, copy);       // Nội dung ban đầu bằng nhau.
assertNotSame(original, copy);       // Root không cùng tham chiếu.
assertNotSame(
    original.get("settings"),
    copy.get("settings")
);                                  // Container con độc lập.
~~~

Không nên dùng == để kiểm tra hai JSON tree có cùng dữ liệu. Ngược lại, chỉ dùng equals() cũng không chứng minh chúng độc lập về tham chiếu. Mỗi phép kiểm tra trả lời một câu hỏi khác nhau.

Với node scalar bất biến, hai bản sao có thể dùng chung một instance. Do đó, không nên yêu cầu mọi node con, kể cả TextNode hoặc IntNode, đều phải khác tham chiếu sau deepCopy(). Hãy tập trung kiểm tra container mutable khi cần chứng minh khả năng chỉnh sửa độc lập.

## 11. Dùng deep copy để tạo snapshot trước khi biến đổi

Một trường hợp phổ biến là nhận JSON gốc, sau đó tạo nhiều phiên bản đầu ra khác nhau.

Ví dụ, hệ thống cần một payload nội bộ giữ đầy đủ dữ liệu và một payload công khai đã loại bỏ thông tin riêng tư:

~~~java
ObjectNode original = (ObjectNode) mapper.readTree(json);

ObjectNode internalPayload = original.deepCopy();

ObjectNode publicPayload = original.deepCopy();
publicPayload.remove("internalNote");
publicPayload.remove("accessToken");
~~~

Hai payload có thể được biến đổi độc lập. Nếu không deep copy, thao tác remove() trên một nhánh có thể làm thay đổi object gốc hoặc nhánh khác nếu cùng dùng một root.

Một ví dụ khác là thêm metadata xử lý mà không sửa dữ liệu nguồn:

~~~java
ObjectNode outgoing = incoming.deepCopy();

outgoing.put("processed", true);
outgoing.put("processedAt", Instant.now().toString());
~~~

incoming vẫn giữ nguyên, còn outgoing chứa thông tin bổ sung.

Snapshot hữu ích khi:

- Một payload cần được gửi đến nhiều hệ thống với cấu trúc khác nhau.
- Cần giữ bản gốc để audit hoặc so sánh.
- Một pipeline có nhiều bước biến đổi độc lập.
- Cần rollback hoặc đối chiếu trước/sau.
- Test cần dữ liệu nền không bị thay đổi giữa các case.

Nếu không cần thay đổi cây, chỉ cần đọc chung một node có thể là đủ. Deep copy nên được tạo khi cần ranh giới sở hữu hoặc biến đổi độc lập, tránh sao chép mọi thứ theo thói quen.

## 12. Sao chép tại ranh giới giữa các thành phần

Khi truyền JsonNode qua nhiều service, hãy xác định ai sở hữu quyền sửa node.

Một số mô hình phổ biến:

**Một chủ sở hữu, các bên khác chỉ đọc.** Thành phần tạo cây giữ quyền sửa; các thành phần khác nhận tham chiếu chỉ để đọc theo quy ước. Đây là cách tiết kiệm bộ nhớ, nhưng quy ước phải được tuân thủ.

**Mỗi thành phần có bản riêng.** Thành phần nhận dữ liệu tạo deep copy trước khi sửa. Cách này rõ ràng về quyền sở hữu và giảm side effect, đổi lại tốn thêm bộ nhớ và thời gian.

**Chuyển giao quyền sở hữu.** Một thành phần tạo cây rồi chuyển nó cho thành phần tiếp theo; thành phần trước không tiếp tục sử dụng hoặc sửa cây. Đây là quy ước kiến trúc, Java không tự cưỡng chế việc chuyển giao.

Có thể mô tả ranh giới:

~~~text
HTTP payload
    |
    v
Parser tạo source tree
    |
    +---------------------+
    |                     |
    v                     v
Deep copy             Read-only view
    |                     |
    v                     v
Transformer A         Validator B
    |
    v
Output tree
~~~

Nếu Validator B chỉ đọc, không cần bản sao riêng. Nếu Validator B có thể sửa node hoặc gọi code không kiểm soát được, hãy xem xét sao chép trước khi chuyển giao.

Một API nhận JsonNode nên ghi rõ node có được phép thay đổi hay không. Vì Java không có kiểu read-only JsonNode chuyên biệt, đây thường là quy ước ở cấp interface, tài liệu và test.

## 13. Chia sẻ JsonNode giữa nhiều luồng

ObjectMapper có thể được chia sẻ giữa nhiều luồng sau khi cấu hình hoàn tất. Điều đó không có nghĩa mọi ObjectNode hoặc ArrayNode cũng an toàn khi nhiều luồng cùng sửa.

Ví dụ nguy hiểm:

~~~java
ObjectNode shared = mapper.createObjectNode();
shared.put("status", "new");

executor.submit(() -> shared.put("status", "worker-a"));
executor.submit(() -> shared.put("status", "worker-b"));
~~~

Hai luồng cùng ghi vào một container mutable. Kết quả phụ thuộc thứ tự thực thi và không thể xem là một quy trình cập nhật được đồng bộ.

Nếu mỗi luồng cần một bản dữ liệu để biến đổi, tạo deep copy trước khi gửi công việc:

~~~java
ObjectNode taskAInput = shared.deepCopy();
ObjectNode taskBInput = shared.deepCopy();

executor.submit(() -> process(taskAInput));
executor.submit(() -> process(taskBInput));
~~~

Mỗi tác vụ có cây riêng. Những thay đổi trong taskAInput không ảnh hưởng taskBInput hoặc shared.

Nếu nhiều luồng chỉ đọc cùng một cây và không có luồng nào sửa nó, việc chia sẻ thường đơn giản hơn. Hãy bảo đảm cây đã được xây dựng hoàn chỉnh trước khi công bố cho các luồng khác và không có mutation diễn ra trong thời gian đọc.

Nếu cần cache JSON tree, có thể lưu một snapshot không bị sửa đổi theo quy ước. Khi một request cần biến đổi dữ liệu cache, tạo deep copy từ snapshot rồi sửa bản riêng. Không để request này thay đổi dữ liệu mà request khác đang đọc.

## 14. Chi phí của deep copy và cách sử dụng hợp lý

Deep copy phải duyệt cấu trúc cây và tạo container mới cho các node có thể thay đổi. Vì vậy, thời gian và bộ nhớ tăng theo kích thước cây và số lượng container.

Nếu cây có nhiều cấp lồng nhau hoặc hàng trăm nghìn phần tử, sao chép liên tục trong mỗi bước có thể tạo áp lực bộ nhớ và garbage collection.

Một số cách giảm chi phí:

- Chỉ deep copy khi cần thay đổi độc lập.
- Nếu chỉ cần đọc, truyền node theo quy ước read-only.
- Nếu chỉ cần thay đổi một phần nhỏ, cân nhắc tạo một object mới chứa phần cần thiết thay vì clone toàn bộ tài liệu.
- Nếu payload rất lớn và cần xử lý tuần tự, xem xét Streaming API thay cho việc giữ toàn bộ tree.
- Tránh deep copy lặp lại cùng một subtree trong một pipeline nếu một bản sao đã đủ cho toàn bộ nhánh xử lý.
- Tạo snapshot ở ranh giới sở hữu rõ ràng, không copy tùy tiện trong mọi helper method.

Ví dụ chỉ cần giữ một phần metadata:

~~~java
ObjectNode result = mapper.createObjectNode();
result.put("orderId", source.path("orderId").asText());

JsonNode metadata = source.get("metadata");

if (metadata != null) {
    result.set("metadata", metadata.deepCopy());
}
~~~

Ở đây, ứng dụng tạo một output mới và chỉ sao chép subtree metadata. Các trường khác không được giữ lại vì chúng không thuộc output cần thiết.

Nếu cần giữ toàn bộ cây rồi sửa nhiều chỗ, deepCopy() ở root thường đơn giản và ít sai sót hơn việc tự sao chép từng nhánh.

## 15. Những giới hạn cần nhớ khi dùng deepCopy()

deepCopy() giải quyết việc tách cấu trúc node, nhưng không làm thay các trách nhiệm khác:

- Không xác thực JSON theo schema.
- Không kiểm tra giá trị nghiệp vụ.
- Không loại bỏ dữ liệu nhạy cảm.
- Không đảm bảo object Java tùy ý nằm trong POJONode được clone.
- Không biến cây thành immutable.
- Không tự đồng bộ truy cập giữa nhiều luồng.
- Không tạo bản sao của mọi tài nguyên bên ngoài mà node tùy biến có thể tham chiếu.

Sau khi deep copy, bản sao vẫn là ObjectNode hoặc ArrayNode có thể thay đổi. Nếu đưa bản sao cho nhiều thành phần cùng sửa, aliasing có thể xuất hiện trở lại bên trong chính bản sao đó.

Vì vậy, deep copy là công cụ để tạo một ranh giới sở hữu mới tại một thời điểm. Nó không phải cơ chế tự động bảo vệ cây khỏi mọi mutation về sau.

## 16. Kiểm tra tính độc lập bằng JUnit

Một test nên chứng minh root và container con được sao chép, rồi xác nhận mutation không lan ngược về nguồn.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

class JsonNodeCopyTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void deepCopySeparatesNestedMutableNodes() {
        ObjectNode original = mapper.createObjectNode();
        original.putObject("settings").put("theme", "light");

        ObjectNode copy = original.deepCopy();

        assertNotSame(original, copy);
        assertNotSame(original.get("settings"), copy.get("settings"));
        assertEquals(original, copy);

        ((ObjectNode) copy.get("settings")).put("theme", "dark");

        assertEquals(
            "light",
            original.path("settings").path("theme").asText()
        );
        assertEquals(
            "dark",
            copy.path("settings").path("theme").asText()
        );
    }

    @Test
    void attachingSameChildSharesMutableReference() {
        ObjectNode child = mapper.createObjectNode();
        child.put("theme", "light");

        ObjectNode first = mapper.createObjectNode();
        ObjectNode second = mapper.createObjectNode();

        first.set("settings", child);
        second.set("settings", child);

        ((ObjectNode) first.get("settings")).put("theme", "dark");

        assertEquals("dark", second.path("settings").path("theme").asText());
    }
}
~~~

Test đầu tiên kiểm tra hai cây ban đầu có nội dung bằng nhau nhưng root và container con không cùng tham chiếu. Sau mutation, giá trị ở hai cây khác nhau.

Test thứ hai xác nhận hành vi chia sẻ tham chiếu khi cùng một node con được gắn vào hai object cha. Đây là kiểm tra quan trọng để tránh hiểu nhầm rằng set() tự tạo bản sao.

Có thể bổ sung test tương tự cho ArrayNode, nested array và snapshot trước khi chạy các transformer khác nhau. Với POJONode hoặc custom node, cần test riêng chiến lược sao chép của object Java được bọc.

## 17. Quy tắc thực hành khi làm việc với cây JSON

Khi nhận một JsonNode, hãy tự xác định:

1. Thành phần nào sở hữu node và có quyền sửa nó?
2. Những thành phần khác chỉ đọc hay cũng có thể sửa?
3. Node có được gắn vào nhiều object hoặc array không?
4. Có cần giữ snapshot của dữ liệu gốc không?
5. Có object Java mutable được bọc trong node đặc biệt không?
6. Cây có đủ nhỏ để deep copy toàn bộ hay chỉ cần copy một subtree?

Một số quy tắc dễ áp dụng:

- Dùng phép gán biến khi muốn chia sẻ cùng một object và chấp nhận mutation chung.
- Dùng set(), add() hoặc setAll() khi muốn gắn node hiện có và chấp nhận chia sẻ tham chiếu.
- Dùng deepCopy() khi cần một cây độc lập để chỉnh sửa.
- Dùng equals() để so sánh nội dung và == hoặc assertNotSame để kiểm tra identity.
- Không sửa một cây đang được các luồng khác đọc.
- Tạo snapshot trước khi truyền node cho code có thể thay đổi dữ liệu.
- Không xem deepCopy() là cơ chế clone sâu cho object Java tùy ý được bọc trong tree.

## Kết luận

ObjectNode và ArrayNode là các container mutable. Việc gán biến, gọi set(), add() hoặc gộp thuộc tính có thể khiến nhiều cây cùng tham chiếu đến một node con. Khi một nhánh sửa node đó, các nhánh còn lại có thể nhìn thấy thay đổi.

Dùng JsonNode.deepCopy() để tạo bản sao đệ quy của cây khi cần snapshot hoặc biến đổi độc lập. Hiểu rằng shallow copy chỉ tạo container mới còn subtree có thể được chia sẻ; các node scalar tiêu chuẩn bất biến có thể được tái sử dụng, nhưng wrapper chứa object Java mutable cần chiến lược riêng. Xác định rõ quyền sở hữu, tránh mutation đồng thời và kiểm tra cả nội dung lẫn identity sẽ giúp quản lý tree model an toàn và dễ dự đoán.

