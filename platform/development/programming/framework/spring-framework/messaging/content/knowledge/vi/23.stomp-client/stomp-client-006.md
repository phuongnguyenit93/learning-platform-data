# Đăng ký, hủy đăng ký và quản lý subscription

## Mục tiêu

Trong ứng dụng WebSocket/STOMP, subscription mô tả việc một client đăng ký nhận message từ một destination. Client gửi frame SUBSCRIBE đến server; khi có message phù hợp, server gửi frame MESSAGE về client. Khi không còn cần nhận dữ liệu, client gửi UNSUBSCRIBE để hủy subscription.

Sau bài này, bạn có thể:

- Tạo subscription bằng thư viện JavaScript @stomp/stompjs.
- Quản lý subscription id và đối tượng StompSubscription.
- Hủy đúng subscription, xử lý nhiều subscription cùng destination.
- Đăng ký lại subscription sau khi reconnect.
- Quản lý subscription theo vòng đời màn hình hoặc tính năng.
- Hiểu receipt, acknowledgment và các giới hạn của Spring simple broker.
- Kiểm thử và chẩn đoán các lỗi thường gặp.

## 1. Subscription trong STOMP là gì?

STOMP là giao thức truyền thông điệp theo frame. Một client có thể vừa gửi message bằng SEND, vừa nhận message bằng cách gửi SUBSCRIBE.

Khi client gửi SUBSCRIBE, frame phải có:

- destination: địa chỉ mà client muốn lắng nghe.
- id: định danh subscription, duy nhất trong phạm vi một kết nối STOMP.
- ack: tùy chọn, chỉ định chế độ xác nhận message là auto, client hoặc client-individual.

Server dùng thông tin này để đăng ký client vào destination. Message phù hợp được gửi lại dưới dạng frame MESSAGE. Mỗi MESSAGE có header subscription cho biết subscription nào đã nhận message.

Khi client gửi UNSUBSCRIBE, frame phải chứa id khớp với subscription đã tạo. Sau khi hủy, server không tiếp tục gửi message qua subscription đó.

STOMP không quy định ý nghĩa nghiệp vụ của destination. Ví dụ /topic/news và /queue/orders là các chuỗi destination; semantics thực tế do server hoặc broker quyết định. Trong Spring, cấu hình message broker thường đăng ký các prefix như /topic và /queue.

## 2. Vòng đời từ kết nối đến hủy subscription

Một vòng đời thường gặp:

1. Tạo STOMP client với endpoint WebSocket.
2. Gọi activate() để bắt đầu kết nối.
3. Chờ server trả frame CONNECTED.
4. Trong callback onConnect, gọi subscribe() cho từng destination cần theo dõi.
5. Khi nhận MESSAGE, xử lý payload trong callback đã đăng ký.
6. Khi màn hình hoặc tính năng không còn cần dữ liệu, gọi unsubscribe() trên subscription tương ứng.
7. Khi ứng dụng kết thúc hoàn toàn, gọi deactivate() để đóng kết nối và dừng reconnect.

Cần phân biệt kết nối WebSocket với subscription. Một kết nối có thể có nhiều subscription. Hủy một subscription không đóng kết nối; đóng kết nối sẽ kết thúc toàn bộ subscription thuộc session đó ở server.

Luồng khái quát:

~~~text
Client                         Spring / STOMP server
  |                                      |
  | -------- CONNECT ------------------> |
  | <------- CONNECTED ----------------- |
  |                                      |
  | -------- SUBSCRIBE ----------------> |
  |          id, destination             |
  |                                      |
  | <------- MESSAGE ------------------- |  Khi có message phù hợp
  |                                      |
  | -------- UNSUBSCRIBE --------------> |
  |                 id                   |
  |                                      |
  | -------- DISCONNECT ---------------> |
~~~

## 3. Tạo subscription bằng @stomp/stompjs

Cài thư viện:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ tối thiểu:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let notificationSubscription;

client.onConnect = () => {
  notificationSubscription = client.subscribe(
    "/topic/notifications",
    (message) => {
      const notification = JSON.parse(message.body);
      console.log("Thông báo mới:", notification);
    }
  );
};

client.onStompError = (frame) => {
  console.error("STOMP error:", frame.headers["message"], frame.body);
};

client.activate();
~~~

Các điểm cần hiểu:

- Client nhận brokerURL là địa chỉ WebSocket endpoint do server đăng ký, ví dụ /ws.
- activate() bắt đầu quá trình kết nối; nó không đồng nghĩa với việc client đã CONNECTED.
- onConnect chỉ được gọi sau khi kết nối STOMP thành công và client nhận frame CONNECTED.
- subscribe(destination, callback, headers) gửi yêu cầu đăng ký và trả về một đối tượng StompSubscription.
- Callback nhận một IMessage. Nội dung thường nằm trong message.body; header có thể đọc qua message.headers.

Hãy gọi subscribe sau khi client kết nối. API Client của @stomp/stompjs kiểm tra trạng thái kết nối khi gọi subscribe; gọi quá sớm có thể phát sinh lỗi vì chưa có STOMP handler đang hoạt động.

## 4. Subscription id và đối tượng StompSubscription

Mỗi subscription có một id. STOMP yêu cầu id khác nhau cho các subscription trên cùng một kết nối. Một client có thể đăng ký cùng destination nhiều lần, nhưng mỗi subscription phải có id riêng.

Với @stomp/stompjs, nếu không truyền id trong headers, thư viện tự tạo id:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body)
);

console.log(subscription.id);
~~~

Có thể đặt id tường minh khi cần đối chiếu với một hệ thống quản lý riêng:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { id: "orders-screen" }
);
~~~

Chỉ dùng id tường minh khi ứng dụng kiểm soát được tính duy nhất của nó trong một connection. Nếu nhiều thành phần cùng dùng id "orders-screen", server có thể từ chối subscription trùng id hoặc việc hủy sẽ nhắm nhầm subscription. Với phần lớn ứng dụng, để thư viện sinh id tự động là lựa chọn đơn giản hơn.

StompSubscription có hai thành phần quan trọng:

- id: id được dùng cho subscription.
- unsubscribe(headers?): phương thức gửi yêu cầu UNSUBSCRIBE cho subscription đó.

Giữ lại đối tượng StompSubscription sau khi subscribe để có thể hủy chính xác khi cần.

## 5. Hủy subscription

Cách ưu tiên là gọi unsubscribe() trên đối tượng trả về từ subscribe():

~~~javascript
const subscription = client.subscribe(
  "/topic/notifications",
  (message) => console.log(message.body)
);

// Khi không còn cần nhận thông báo:
subscription.unsubscribe();
~~~

Có thể truyền thêm header cho frame UNSUBSCRIBE:

~~~javascript
subscription.unsubscribe({
  receipt: "unsubscribe-notifications-1"
});
~~~

Một cách khác là gọi trực tiếp client.unsubscribe(id):

~~~javascript
client.unsubscribe(subscription.id);
~~~

Cách trực tiếp hữu ích khi ứng dụng chỉ lưu id thay vì lưu toàn bộ đối tượng. Tuy nhiên, lưu đối tượng subscription thường giúp code dễ đọc và ít nhầm id hơn.

UNSUBSCRIBE chỉ hủy một subscription có id tương ứng. Nếu cùng destination có ba subscription với ba id khác nhau, hủy một subscription không tự động hủy hai subscription còn lại.

Hãy chỉ gọi unsubscribe khi client còn kết nối. Khi WebSocket đã đóng, server sẽ dọn subscription gắn với session đã kết thúc; đối tượng subscription cũ không còn đại diện cho một đăng ký đang hoạt động trên connection mới.

## 6. Quản lý nhiều subscription

Khi một màn hình cần nhận nhiều loại sự kiện, lưu subscription trong Map giúp quản lý vòng đời rõ ràng:

~~~javascript
const subscriptions = new Map();

function addSubscription(key, destination, callback) {
  if (!client.connected) {
    throw new Error("STOMP client chưa kết nối");
  }

  if (subscriptions.has(key)) {
    return subscriptions.get(key);
  }

  const subscription = client.subscribe(destination, callback);
  subscriptions.set(key, subscription);
  return subscription;
}

function removeSubscription(key) {
  const subscription = subscriptions.get(key);

  if (!subscription) {
    return;
  }

  if (client.connected) {
    subscription.unsubscribe();
  }

  subscriptions.delete(key);
}
~~~

Sử dụng:

~~~javascript
addSubscription(
  "orders",
  "/topic/orders",
  (message) => renderOrder(JSON.parse(message.body))
);

addSubscription(
  "alerts",
  "/user/queue/alerts",
  (message) => renderAlert(JSON.parse(message.body))
);

// Khi rời màn hình:
removeSubscription("orders");
removeSubscription("alerts");
~~~

Key trong Map là tên do ứng dụng chọn để quản lý tính năng; destination là địa chỉ STOMP; subscription.id là id giao thức do thư viện sinh ra hoặc do ứng dụng cung cấp. Ba khái niệm này có mục đích khác nhau.

Hàm addSubscription ở ví dụ trên chủ động từ chối đăng ký khi client chưa kết nối. Nếu ứng dụng cần ghi nhớ mong muốn subscribe trước khi kết nối, hãy lưu cấu hình mong muốn riêng rồi thực hiện đăng ký trong onConnect.

## 7. Không đăng ký trùng lặp

Một lỗi phổ biến là gọi subscribe mỗi lần component render hoặc mỗi lần một hàm khởi tạo được gọi lại. Sau vài lần render, một message có thể kích hoạt callback nhiều lần vì có nhiều subscription cùng destination.

Cách phòng tránh:

- Đặt thao tác subscribe ở nơi có vòng đời rõ ràng, ví dụ sau khi kết nối hoặc khi màn hình được mount.
- Lưu handle trả về từ subscribe.
- Kiểm tra trạng thái hiện tại trước khi tạo subscription mới.
- Hủy subscription khi component hoặc màn hình không còn dùng.
- Dùng id khác nhau cho các subscription độc lập.
- Tránh tạo một subscription toàn cục mới mỗi lần một sự kiện UI xảy ra.

Hai subscription cùng destination có thể là chủ đích, ví dụ hai phần giao diện độc lập cùng theo dõi một topic. Khi đó cần quản lý chúng như hai đăng ký riêng và hủy riêng.

## 8. Reconnect và đăng ký lại subscription

Khi kết nối bị mất, session STOMP cũ kết thúc và subscription của session đó không còn hiệu lực. @stomp/stompjs có thể tự kết nối lại theo reconnectDelay, nhưng ứng dụng vẫn phải đăng ký lại các destination cần thiết trong onConnect.

Ví dụ:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let ordersSubscription;
let alertsSubscription;

client.onConnect = () => {
  // onConnect chạy lại sau mỗi lần reconnect thành công.
  ordersSubscription = client.subscribe(
    "/topic/orders",
    (message) => renderOrder(JSON.parse(message.body))
  );

  alertsSubscription = client.subscribe(
    "/user/queue/alerts",
    (message) => renderAlert(JSON.parse(message.body))
  );
};

client.onWebSocketClose = () => {
  // Handle của session cũ không còn đại diện cho subscription đang hoạt động.
  ordersSubscription = undefined;
  alertsSubscription = undefined;
};

client.activate();
~~~

Không chỉ gọi subscribe một lần trước client.activate() rồi giả định thư viện tự khôi phục mọi đăng ký. Hãy đặt logic subscribe trong onConnect hoặc dùng một lớp quản lý subscription có thể tái tạo đăng ký sau mỗi kết nối.

Nếu có subscription động, lưu danh sách destination mà người dùng đang muốn theo dõi. Khi reconnect thành công, lặp qua danh sách đó và tạo subscription mới. Khi người dùng bỏ theo dõi trong lúc mất kết nối, xóa destination khỏi danh sách mong muốn để nó không được đăng ký lại ở lần kết nối sau.

Ví dụ mô hình quản lý theo nhu cầu:

~~~javascript
const desiredSubscriptions = new Map();
let liveSubscriptions = new Map();

function watch(key, destination, callback) {
  desiredSubscriptions.set(key, { destination, callback });

  if (client.connected && !liveSubscriptions.has(key)) {
    const subscription = client.subscribe(destination, callback);
    liveSubscriptions.set(key, subscription);
  }
}

function unwatch(key) {
  desiredSubscriptions.delete(key);

  const subscription = liveSubscriptions.get(key);
  if (client.connected) {
    subscription?.unsubscribe();
  }

  liveSubscriptions.delete(key);
}

client.onConnect = () => {
  liveSubscriptions.clear();

  for (const [key, item] of desiredSubscriptions) {
    const subscription = client.subscribe(
      item.destination,
      item.callback
    );
    liveSubscriptions.set(key, subscription);
  }
};

client.onWebSocketClose = () => {
  liveSubscriptions.clear();
};
~~~

Trong ví dụ này, desiredSubscriptions là trạng thái nghiệp vụ mà ứng dụng muốn duy trì. liveSubscriptions chỉ chứa handle của connection hiện tại. Tách hai loại trạng thái giúp ứng dụng phục hồi đăng ký sau reconnect mà không giữ nhầm handle của session cũ.

## 9. Quản lý subscription theo vòng đời UI

Với giao diện dạng SPA, subscription thường gắn với một màn hình hoặc component. Khi màn hình xuất hiện, đăng ký nhận dữ liệu; khi màn hình bị hủy, hủy subscription.

Ví dụ theo dạng hàm khởi tạo và cleanup:

~~~javascript
function mountOrdersScreen(client) {
  const subscription = client.subscribe(
    "/topic/orders",
    (message) => renderOrder(JSON.parse(message.body))
  );

  return function cleanup() {
    if (client.connected) {
      subscription.unsubscribe();
    }
  };
}
~~~

Sử dụng:

~~~javascript
const cleanupOrders = mountOrdersScreen(client);

// Khi rời màn hình:
cleanupOrders();
~~~

Trong React, có thể gọi logic tương tự từ useEffect và trả về cleanup function. Cần lưu ý client phải kết nối trước khi effect subscribe. Nếu kết nối đến sau khi component đã mount, hãy tích hợp component với trạng thái kết nối và thực hiện subscribe khi onConnect hoặc khi trạng thái chuyển sang connected.

Không đặt subscribe trực tiếp trong thân component vì thân component có thể chạy nhiều lần. Dùng effect hoặc một service quản lý vòng đời để tránh đăng ký lặp.

## 10. Receipt và xác nhận đăng ký

STOMP cho phép client thêm header receipt vào frame, sau đó server có thể trả frame RECEIPT để xác nhận đã xử lý frame tương ứng.

Với @stomp/stompjs, có thể đăng ký callback bằng watchForReceipt trước khi gửi frame có header receipt:

~~~javascript
const receiptId = "orders-subscribe-001";

client.watchForReceipt(receiptId, (frame) => {
  console.log("Server đã xác nhận:", frame.headers["receipt-id"]);
});

const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { receipt: receiptId }
);
~~~

Receipt hữu ích khi ứng dụng cần xác nhận server đã xử lý một frame trước khi thực hiện bước tiếp theo. Receipt là xác nhận ở tầng giao thức; nó không chứng minh callback phía client đã xử lý message, không xác nhận giao dịch nghiệp vụ đã commit và cũng không mặc định chứng minh dữ liệu đã được lưu bền vững.

Không phải broker nào cũng hỗ trợ receipt. Spring simple broker chỉ hỗ trợ một tập con của STOMP và không hỗ trợ receipt. Nếu dùng simple broker, không xây dựng luồng ứng dụng phụ thuộc vào RECEIPT. Hãy kiểm tra khả năng của broker đang dùng trước khi triển khai.

Nếu cần biết thời điểm Spring đã xử lý xong SUBSCRIBE với simple broker, có thể theo dõi brokerChannel bằng ExecutorChannelInterceptor và xử lý trong afterMessageHandled. SessionSubscribeEvent chỉ thông báo Spring nhận được frame SUBSCRIBE; nó không phải receipt xác nhận broker đã hoàn tất xử lý đăng ký.

## 11. Acknowledgment khi nhận message

Header ack của SUBSCRIBE xác định cách client xác nhận message:

| Chế độ | Ý nghĩa |
| --- | --- |
| auto | Server xem message đã được giao khi gửi cho client; client không cần gửi ACK. |
| client | Client gửi ACK sau khi xử lý; ACK có tính tích lũy trong subscription. |
| client-individual | Client xác nhận từng message riêng lẻ. |

Ví dụ dùng @stomp/stompjs với broker hỗ trợ acknowledgment:

~~~javascript
const subscription = client.subscribe(
  "/queue/tasks",
  async (message) => {
    try {
      await processTask(JSON.parse(message.body));
      message.ack();
    } catch (error) {
      message.nack();
    }
  },
  { ack: "client-individual" }
);
~~~

ACK chỉ nên gửi sau khi ứng dụng hoàn tất bước xử lý mà nó muốn xác nhận. Nếu ACK trước khi lưu dữ liệu hoặc hoàn thành công việc, lỗi xảy ra sau đó có thể làm ứng dụng mất cơ hội xử lý lại message.

Khi broker hỗ trợ redelivery, message chưa được ACK có thể được giao lại sau khi kết nối mất. Vì vậy, consumer nên thiết kế xử lý idempotent: nếu cùng một message đến lần thứ hai, kết quả nghiệp vụ vẫn đúng.

Khả năng ACK/NACK phụ thuộc broker. Spring simple broker không hỗ trợ acknowledgment mode client/client-individual; nó chỉ đáp ứng tập con STOMP đơn giản. Nếu cần ACK, NACK hoặc redelivery, hãy dùng broker relay đến broker chuyên dụng và kiểm tra semantics cụ thể của broker đó.

## 12. Đóng client và dọn subscription

Khi chỉ muốn dừng nhận một loại message nhưng vẫn giữ kết nối, gọi subscription.unsubscribe().

Khi muốn dừng toàn bộ client và ngăn reconnect, gọi:

~~~javascript
await client.deactivate();
~~~

deactivate() thực hiện quá trình ngắt kết nối và trả về Promise hoàn tất khi quá trình deactivation kết thúc. Đây là cách phù hợp khi ứng dụng rời trang, đăng xuất hoặc không còn cần STOMP client.

Không cần gửi UNSUBSCRIBE riêng cho từng subscription trước khi đóng toàn bộ connection. Khi session kết thúc, server dọn subscription gắn với session đó. Tuy nhiên, nếu vẫn giữ kết nối để dùng các destination khác, phải hủy từng subscription không còn cần.

Không dùng forceDisconnect() cho luồng đóng bình thường. API này đóng WebSocket trực tiếp, bỏ qua trình tự DISCONNECT STOMP và có thể khiến server phát hiện mất kết nối muộn hơn. Chỉ dùng trong tình huống phục hồi đặc biệt khi kết nối không thể đóng theo quy trình bình thường.

## 13. Bảo mật và kiểm soát destination

Biết destination không đồng nghĩa có quyền subscribe destination đó. Server phải xác thực người dùng và kiểm tra quyền SUBSCRIBE.

Các điểm cần lưu ý:

- Không cho phép mọi người subscribe mọi topic chỉ vì destination không chứa dữ liệu bí mật.
- Kiểm tra quyền theo người dùng, tenant, room hoặc tài nguyên.
- Dùng destination riêng cho dữ liệu cá nhân, ví dụ /user/queue/notifications khi phù hợp với cấu hình Spring.
- Không tin userId, role hoặc tenantId do client tự truyền trong header/payload.
- Giới hạn số lượng subscription và phạm vi wildcard để tránh client tạo quá nhiều đăng ký.
- Khi đăng xuất, đóng client và xóa trạng thái subscription ở tầng giao diện.
- Không ghi token, cookie hoặc payload nhạy cảm vào log STOMP debug.

Nếu dùng Spring Security, cấu hình message authorization cho các destination SEND và SUBSCRIBE. Quy tắc phân quyền phải áp dụng cả với message đi vào controller và message đi thẳng đến broker.

## 14. Kiểm thử subscription

Một integration test nên xác minh cả việc đăng ký lẫn hủy:

1. Khởi chạy Spring application với WebSocket/STOMP endpoint.
2. Kết nối STOMP client và đợi onConnect.
3. Subscribe destination /topic/test.
4. Gửi message từ server đến /topic/test.
5. Xác nhận callback nhận đúng payload.
6. Gọi subscription.unsubscribe().
7. Gửi message tiếp theo đến /topic/test.
8. Xác nhận callback của subscription đã hủy không nhận message mới.
9. Tạo lại kết nối, xác nhận onConnect đăng ký lại destination cần thiết.

Các ca kiểm thử bổ sung:

- Hai subscription cùng destination nhưng id khác nhau.
- Hai subscription cùng destination nhưng chỉ hủy một.
- Cố ý đăng ký id trùng trong cùng session.
- Subscribe khi client chưa connected.
- Mất kết nối đột ngột và reconnect.
- Người dùng hủy subscription khi đang offline.
- Broker từ chối destination hoặc frame không hợp lệ.
- Client không có quyền SUBSCRIBE destination riêng tư.
- Receipt hoặc ACK chỉ khi broker được kiểm thử có hỗ trợ tính năng đó.

Để kiểm thử logic callback, có thể mock message handler. Nhưng để kiểm chứng destination, frame SUBSCRIBE/UNSUBSCRIBE, reconnect và security, cần integration test với STOMP endpoint thực tế.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| subscribe() báo client chưa kết nối | Gọi subscribe trước CONNECTED | Chuyển thao tác vào onConnect hoặc chờ trạng thái connected. |
| Một message gọi callback nhiều lần | Có nhiều subscription cùng destination | Lưu handle, ngăn đăng ký trùng và hủy subscription cũ. |
| unsubscribe() không hủy đúng đăng ký | Dùng sai id hoặc quản lý nhầm handle | Gọi unsubscribe() trên đúng đối tượng StompSubscription. |
| Reconnect thành công nhưng không nhận message | Chưa subscribe lại sau CONNECTED mới | Đăng ký lại trong onConnect mỗi lần kết nối thành công. |
| Message đến sau khi rời màn hình | Cleanup không chạy hoặc handle không được lưu | Gắn subscription với vòng đời component và gọi cleanup. |
| Receipt callback không chạy | Broker không hỗ trợ receipt hoặc đăng ký watcher sai thời điểm | Kiểm tra broker; gọi watchForReceipt trước frame có receipt. |
| ACK/NACK bị từ chối | Broker không hỗ trợ ack mode được chọn | Kiểm tra khả năng broker; Spring simple broker không hỗ trợ ACK/NACK. |
| Client nhận message của tenant khác | Server không kiểm tra quyền SUBSCRIBE | Áp dụng authorization trên destination và xác thực người dùng. |
| Subscription cũ được tạo lại sau reconnect dù người dùng đã bỏ theo dõi | Danh sách subscription mong muốn chưa được cập nhật | Xóa destination khỏi desiredSubscriptions khi hủy. |

## 16. Ghi nhớ

- SUBSCRIBE đăng ký nhận message; UNSUBSCRIBE hủy một subscription theo id.
- Mỗi subscription trong cùng connection cần id riêng; @stomp/stompjs tự sinh id nếu không truyền id.
- subscribe() trả về StompSubscription; ưu tiên gọi unsubscribe() trên handle này.
- Gọi subscribe sau CONNECTED; dùng onConnect để đăng ký lại sau mỗi lần reconnect.
- Lưu trạng thái mong muốn và handle của connection hiện tại riêng biệt khi quản lý subscription động.
- Receipt, ACK và NACK phụ thuộc broker; Spring simple broker không hỗ trợ receipt hoặc acknowledgment.
- Hủy subscription theo vòng đời màn hình; dùng deactivate() khi cần đóng toàn bộ STOMP client.
- Bảo mật SUBSCRIBE quan trọng như bảo mật SEND; server phải kiểm tra quyền truy cập destination.

## Tài liệu tham khảo

- [@stomp/stompjs — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html)
- [@stomp/stompjs — StompSubscription API](https://stomp-js.github.io/api-docs/latest/interfaces/StompSubscription.html)
- [STOMP Protocol Specification 1.2 — SUBSCRIBE](https://stomp.github.io/stomp-specification-1.2.html#SUBSCRIBE)
- [STOMP Protocol Specification 1.2 — UNSUBSCRIBE](https://stomp.github.io/stomp-specification-1.2.html#UNSUBSCRIBE)
- [STOMP Protocol Specification 1.2 — ACK and NACK](https://stomp.github.io/stomp-specification-1.2.html#ACK)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)

